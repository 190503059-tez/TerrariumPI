# -*- coding: utf-8 -*-
import terrariumLogging
logger = terrariumLogging.logging.getLogger(__name__)

import asyncio
import contextlib
import threading
import socket

from time import sleep, time

from datetime import datetime

from terrariumUtils import terrariumCache, terrariumUtils, terrariumSingleton, terrariumAsync

# pip install meross-iot
# https://github.com/albertogeniola/MerossIot
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager
from meross_iot.controller.mixins.toggle import ToggleXMixin
from meross_iot.model.http.exception import BadLoginException
from meross_iot.model.exception import CommandTimeoutError
from meross_iot.model.enums import OnlineStatus, Namespace


class TerrariumMerossCloud(terrariumSingleton):

  def __init__(self, username, password):

    self.__engine = { 'cache' : terrariumCache(), 'running': False, 'reconnecting': False, 'restart_counter' : 0, 'error': False, 'event': None , 'asyncio' : terrariumAsync()}

    self._data = {}
    self._username = username
    self._password = password

    self.start()

  def start(self, reconnecting = False):

    def _run():
      data = asyncio.run_coroutine_threadsafe(self._main_process(), self.__engine['asyncio'].async_loop)
      data.result()

    start_time = time()
    self.__engine['error']  = False
    self.__engine['event']  = asyncio.Event()
    self.__engine['thread'] = threading.Thread(target=_run)
    self.__engine['thread'].start()

    if reconnecting:
      logger.info('Reconnecting to the Meross cloud')

    while not self.__engine['running'] and not self.__engine['error']:
      logger.info('Waiting for Meross cloud connection ... ')
      sleep(1)

    if not self.__engine['error']:
      logger.info(f'Meross cloud is {"re-" if reconnecting else ""}connected! Found {len(self._data)} devices in {time()-start_time:.2f} seconds.')

  def _store_data(self):
    for key in self._data:
      self.__engine['cache'].set_data(key, self._data[key],90)

  def scan_hardware(self,type):

    async def _scan_hardware(type):
      await self.manager.async_device_discovery()
      meross_devices = []
      if 'sensors' == type:
        meross_devices = self.manager.find_devices(device_type='ms100')
      elif 'relays' == type:
        meross_devices = self.manager.find_devices(device_class=ToggleXMixin)

      return meross_devices

    if not self.__engine['running']:
      return []

    data = asyncio.run_coroutine_threadsafe(_scan_hardware(type), self.__engine['asyncio'].async_loop)
    devices = data.result()
    return devices

  def toggle_relay(self, device, switch, state):
    TIMEOUT = 5

    async def _toggle_relay(device, switch, state):

      device = self.manager.find_devices(device_uuids=[device])
      if len(device) == 1:
        device = device[0]

        if state != 0.0:
          await device.async_turn_on(channel=switch, timeout=TIMEOUT+1)
        else:
          await device.async_turn_off(channel=switch, timeout=TIMEOUT+1)

        return True

      return None

    if not self.__engine['running']:
      return None

    # Create a timer for offline detection...
    offline = threading.Timer(TIMEOUT, self.reconnect)
    offline.start()

    # Start the toggle action
    data = asyncio.run_coroutine_threadsafe(_toggle_relay(device, switch, state), self.__engine['asyncio'].async_loop)
    result = data.result()

    # Stop the offline detection
    offline.cancel()

    return result

  def stop(self):
    logger.info('Stopping Meross cloud ... ')
    self.__engine['running'] = False
    self.__engine['event'].set()
    self.__engine['thread'].join()

  def reconnect(self):
    if self.__engine['reconnecting']:
      return

    self.__engine['reconnecting'] = True
    logger.warning('Reconnecting to Meross cloud. Somehow the connection was lost ...')
    self.stop()
    self.start(True)

  async def _main_process(self):

    # https://stackoverflow.com/a/49632779
    async def event_wait(evt, timeout):
      # suppress TimeoutError because we'll return False in case of timeout
      with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(evt.wait(), timeout)
      return evt.is_set()

    async def _notification(push_notification, target_devices):
      logger.info('Got an update from the Meross Cloud.')
#      print(push_notification)
#      print(dir(push_notification))
#      print(f'namespace: {push_notification.namespace}')

      if push_notification.namespace == Namespace.SYSTEM_ONLINE:
        # Connection issues...
#        print(f'status: {push_notification.status}')

        if push_notification.status == OnlineStatus.ONLINE:
          # Reconnect
          self.reconnect()

      else:
        for device in target_devices:
          if hasattr(device,'is_on'):
            self._data[f'{device.uuid}'] = []

            for channel in device.channels:
              self._data[f'{device.uuid}'].append(device.is_on(channel=channel.index))

          if hasattr(device,'last_sampled_temperature'):
            self._data[f'{device.subdevice_id}'] = {
              'temperature' : device.last_sampled_temperature,
              'humidity'    : device.last_sampled_humidity
            }

        self._store_data()

    try:
      # Setup the HTTP client API from user-password
      http_api_client = await MerossHttpClient.async_from_user_password(email=self._username, password=self._password)

      # Setup and start the device manager
      self.manager = MerossManager(http_client=http_api_client)
      await self.manager.async_init()

      # Discover devices.
      await self.manager.async_device_discovery()
      meross_devices = self.manager.find_devices()
      for dev in meross_devices:

        # Is a relay
        if hasattr(dev,'is_on'):
          await dev.async_update()
          self._data[f'{dev.uuid}'] = []

          for channel in dev.channels:
            self._data[f'{dev.uuid}'].append(dev.is_on(channel=channel.index))

        # Is a sensor
        if hasattr(dev,'last_sampled_temperature'):
          await dev.async_update()
          #print(f'Last data: {dev.last_sampled_time}')
          self._data[f'{dev.subdevice_id}'] = {
            'temperature' : dev.last_sampled_temperature,
            'humidity'    : dev.last_sampled_humidity
          }

      self._store_data()
      self.__engine['running'] = True
      self.__engine['reconnecting'] = False
      self.__engine['restart_counter'] = 0
      self.manager.register_push_notification_handler_coroutine(_notification)

      while not await event_wait(self.__engine['event'], 30):
        self._store_data()

    except CommandTimeoutError:
      logger.error(f'Meross communication timed out connecting with the server.')
    except BadLoginException:
      logger.error(f'Wrong login credentials for Meross. Please check your settings!')
    except socket.timeout:
      self.__engine['error'] = True
      if self.__engine['restart_counter'] < 10:
        self.__engine['restart_counter'] += 1
        logger.error(f'Timeout logging into Meross Cloud. Reconnecting in 5 seconds attempt {self.__engine["restart_counter"]} ...')
        threading.Timer(5,self.start).start()
      else:
        logger.error('Failed to connect to the Meross Cloud after 10 times. Please check your network configuration.')

    finally:
      # Close the manager and logout from http_api
      self.manager.close()
      await http_api_client.async_logout()
      logger.info('Closed Meross cloud connection')