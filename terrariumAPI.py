# -*- coding: utf-8 -*-
import terrariumLogging
logger = terrariumLogging.logging.getLogger(__name__)

import copy
import json

from datetime import datetime, timezone, timedelta
from pony import orm
from bottle import request, response, static_file, HTTPError
from json import dumps
from pathlib import Path
from tinytag import TinyTag
from hashlib import md5

from apispec import APISpec
from apispec_webframeworks.bottle import BottlePlugin

from terrariumArea      import terrariumArea
from terrariumEnclosure import terrariumEnclosure
from terrariumDatabase  import Area, Audiofile, Button, ButtonHistory, Enclosure, Relay, RelayHistory, Sensor, SensorHistory, Setting, Webcam
from terrariumCalendar  import terrariumCalendar
from hardware.sensor    import terrariumSensor
from hardware.relay     import terrariumRelay
from hardware.button    import terrariumButton
from hardware.webcam    import terrariumWebcam

from terrariumUtils import terrariumUtils


class terrariumAPI(object):

  def __init__(self, webserver):
    self.webserver = webserver
    self.apispec = APISpec(
        title=self.webserver.engine.settings['title'],
        version=self.webserver.engine.version,
        openapi_version='3.0.2',
        info=dict(description=f'{self.webserver.engine.settings["title"]} API'),
        plugins=[BottlePlugin()],
    )

  # Always (force = True) enable authentication on the API
  def authentication(self, force = True):
    return self.webserver.authenticate(force)

  def routes(self,bottle_app):

    # Area API
    bottle_app.route('/api/areas/types/', 'GET',    self.area_types, apply=self.authentication(False), name='api:area_types')
    bottle_app.route('/api/areas/<area:path>/', 'GET',    self.area_detail, apply=self.authentication(False), name='api:area_detail')
    bottle_app.route('/api/areas/<area:path>/', 'PUT',    self.area_update, apply=self.authentication(),      name='api:area_update')
    bottle_app.route('/api/areas/<area:path>/', 'DELETE', self.area_delete, apply=self.authentication(),      name='api:area_delete')
    bottle_app.route('/api/areas/',                  'GET',    self.area_list,   apply=self.authentication(False), name='api:area_list')
    bottle_app.route('/api/areas/',                  'POST',   self.area_add,    apply=self.authentication(),      name='api:area_add')


    # Audio API
    bottle_app.route('/api/audiofiles/<audiofile:path>/', 'GET',    self.audiofile_detail,   apply=self.authentication(False), name='api:audiofile_detail')
    bottle_app.route('/api/audiofiles/<audiofile:path>/', 'DELETE', self.audiofile_delete,   apply=self.authentication(),      name='api:audiofile_delete')
    bottle_app.route('/api/audiofiles/',                  'GET',    self.audiofile_list,     apply=self.authentication(False), name='api:audiofile_list')
    bottle_app.route('/api/audiofiles/',                  'POST',   self.audiofile_add,      apply=self.authentication(),      name='api:audiofile_add')


    # Buttons API
    bottle_app.route('/api/buttons/<button:path>/history/<period:re:(day|week|month|year)>/', 'GET', self.button_history, apply=self.authentication(False), name='api:button_history_period')
    bottle_app.route('/api/buttons/<button:path>/history/', 'GET',    self.button_history,  apply=self.authentication(False), name='api:button_history')
    bottle_app.route('/api/buttons/hardware/',              'GET',    self.button_hardware, apply=self.authentication(),      name='api:button_hardware')
    bottle_app.route('/api/buttons/<button:path>/',         'GET',    self.button_detail,   apply=self.authentication(False), name='api:button_detail')
    bottle_app.route('/api/buttons/<button:path>/',         'PUT',    self.button_update,   apply=self.authentication(),      name='api:button_update')
    bottle_app.route('/api/buttons/<button:path>/',         'DELETE', self.button_delete,   apply=self.authentication(),      name='api:button_delete')
    bottle_app.route('/api/buttons/',                       'GET',    self.button_list,     apply=self.authentication(False), name='api:button_list')
    bottle_app.route('/api/buttons/',                       'POST',   self.button_add,      apply=self.authentication(),      name='api:button_add')


    # Calendar API
    bottle_app.route('/api/calendar/<calendar:path>/', 'GET',    self.calendar_detail,   apply=self.authentication(False), name='api:calendar_detail')
    bottle_app.route('/api/calendar/<calendar:path>/', 'PUT',    self.calendar_update,   apply=self.authentication(),      name='api:calendar_update')
    bottle_app.route('/api/calendar/<calendar:path>/', 'DELETE', self.calendar_delete,   apply=self.authentication(),      name='api:calendar_delete')
    bottle_app.route('/api/calendar/download/',        'GET',    self.calendar_download, apply=self.authentication(),      name='api:calendar_download')
    bottle_app.route('/api/calendar/',                 'GET',    self.calendar_list,     apply=self.authentication(False), name='api:calendar_list')
    bottle_app.route('/api/calendar/',                 'POST',   self.calendar_add,      apply=self.authentication(),      name='api:calendar_add')


    # Enclosure API
    # bottle_app.route('/api/enclosures/<relay:path>/history/<period:re:(day|week|month|year)>/', 'GET', self.relay_history, apply=self.authentication(False), name='api:relay_history_period')
    # bottle_app.route('/api/enclosures/<relay:path>/history/', 'GET',    self.relay_history,  apply=self.authentication(False), name='api:relay_history')
    # bottle_app.route('/api/enclosures/<relay:path>/<action:re:(toggle|on|off|\d+)>/', 'POST',    self.relay_action,  apply=self.authentication(), name='api:relay_action')

    # bottle_app.route('/api/enclosures/<relay:path>/manual/', 'POST',    self.relay_manual,  apply=self.authentication(), name='api:relay_manual')

    bottle_app.route('/api/enclosures/<enclosure:path>/', 'GET',    self.enclosure_detail, apply=self.authentication(False), name='api:enclosure_detail')
    bottle_app.route('/api/enclosures/<enclosure:path>/', 'PUT',    self.enclosure_update, apply=self.authentication(),      name='api:enclosure_update')
    bottle_app.route('/api/enclosures/<enclosure:path>/', 'DELETE', self.enclosure_delete, apply=self.authentication(),      name='api:enclosure_delete')
    bottle_app.route('/api/enclosures/',                  'GET',    self.enclosure_list,   apply=self.authentication(False), name='api:enclosure_list')
    bottle_app.route('/api/enclosures/',                  'POST',   self.enclosure_add,    apply=self.authentication(),      name='api:enclosure_add')


    # Logfile API
    bottle_app.route('/api/logfile/download/', 'GET', self.logfile_download, apply=self.authentication(), name='api:logfile_download')


    # Reboot/start API
    bottle_app.route('/api/<action:re:(restart|reboot|shutdown)>/',   'POST', self.server_action, apply=self.authentication(), name='api:server_action')


    # Relays API

    bottle_app.route('/api/relays/<relay:path>/<action:re:(history)>/<period:re:(day|week|month|year)>/', 'GET', self.relay_history, apply=self.authentication(False), name='api:relay_history_period')
    bottle_app.route('/api/relays/<relay:path>/<action:re:(history)>/', 'GET',    self.relay_history,  apply=self.authentication(False), name='api:relay_history')

    bottle_app.route('/api/relays/<relay:path>/<action:re:(export)>/<period:re:(day|week|month|year)>/',  'GET', self.relay_history, apply=self.authentication(),      name='api:relay_export_period')
    bottle_app.route('/api/relays/<relay:path>/<action:re:(export)>/',  'GET',    self.relay_history,  apply=self.authentication(),      name='api:relay_export')


    bottle_app.route('/api/relays/<relay:path>/<action:re:(toggle|on|off|\d+)>/', 'POST',    self.relay_action,  apply=self.authentication(), name='api:relay_action')

    bottle_app.route('/api/relays/<relay:path>/manual/', 'POST',    self.relay_manual,  apply=self.authentication(), name='api:relay_manual')


    bottle_app.route('/api/relays/hardware/',             'GET',    self.relay_hardware, apply=self.authentication(),      name='api:relay_hardware')
    bottle_app.route('/api/relays/<relay:path>/',         'GET',    self.relay_detail,   apply=self.authentication(False), name='api:relay_detail')
    bottle_app.route('/api/relays/<relay:path>/',         'PUT',    self.relay_update,   apply=self.authentication(),      name='api:relay_update')
    bottle_app.route('/api/relays/<relay:path>/',         'DELETE', self.relay_delete,   apply=self.authentication(),      name='api:relay_delete')
    bottle_app.route('/api/relays/',                      'GET',    self.relay_list,     apply=self.authentication(False), name='api:relay_list')
    bottle_app.route('/api/relays/',                      'POST',   self.relay_add,      apply=self.authentication(),      name='api:relay_add')


    # Sensors API
    all_sensor_types = '|'.join(terrariumSensor.sensor_types)
    bottle_app.route(f'/api/sensors/<filter:re:({all_sensor_types})>/<action:re:(history)>/<period:re:(day|week|month|year)>/', 'GET', self.sensor_history, apply=self.authentication(False), name='api:sensor_type_history_period')
    bottle_app.route(f'/api/sensors/<filter:re:({all_sensor_types})>/<action:re:(export)>/<period:re:(day|week|month|year)>/',  'GET', self.sensor_history, apply=self.authentication(),      name='api:sensor_type_export_period')
    bottle_app.route(f'/api/sensors/<filter:re:({all_sensor_types})>/<action:re:(history)>/', 'GET', self.sensor_history, apply=self.authentication(False), name='api:sensor_type_history')
    bottle_app.route(f'/api/sensors/<filter:re:({all_sensor_types})>/<action:re:(export)>/',  'GET', self.sensor_history, apply=self.authentication(),      name='api:sensor_type_export')
    bottle_app.route(f'/api/sensors/<filter:re:({all_sensor_types})>/',                       'GET', self.sensor_list,    apply=self.authentication(False), name='api:sensor_list_filtered')
    bottle_app.route('/api/sensors/<filter:path>/<action:re:(history)>/<period:re:(day|week|month|year)>/', 'GET', self.sensor_history, apply=self.authentication(False), name='api:sensor_history_period')
    bottle_app.route('/api/sensors/<filter:path>/<action:re:(export)>/<period:re:(day|week|month|year)>/',  'GET', self.sensor_history, apply=self.authentication(),      name='api:sensor_export_period')
    bottle_app.route('/api/sensors/<filter:path>/<action:re:(history)>/', 'GET',    self.sensor_history,  apply=self.authentication(False), name='api:sensor_history')
    bottle_app.route('/api/sensors/<filter:path>/<action:re:(export)>/',  'GET',    self.sensor_history,  apply=self.authentication(),      name='api:sensor_export')
    bottle_app.route('/api/sensors/hardware/',      'GET',    self.sensor_hardware, apply=self.authentication(),      name='api:sensor_hardware')
    bottle_app.route('/api/sensors/<sensor:path>/', 'GET',    self.sensor_detail,   apply=self.authentication(False), name='api:sensor_detail')
    bottle_app.route('/api/sensors/<sensor:path>/', 'PUT',    self.sensor_update,   apply=self.authentication(),      name='api:sensor_update')
    bottle_app.route('/api/sensors/<sensor:path>/', 'DELETE', self.sensor_delete,   apply=self.authentication(),      name='api:sensor_delete')
    bottle_app.route('/api/sensors/',               'GET',    self.sensor_list,     apply=self.authentication(False), name='api:sensor_list')
    bottle_app.route('/api/sensors/',               'POST',   self.sensor_add,      apply=self.authentication(),      name='api:sensor_add')

    # Settings API
    bottle_app.route('/api/settings/<setting:path>/', 'GET',    self.setting_detail, apply=self.authentication(), name='api:setting_detail')
    bottle_app.route('/api/settings/<setting:path>/', 'PUT',    self.setting_update, apply=self.authentication(), name='api:setting_update')
    bottle_app.route('/api/settings/<setting:path>/', 'DELETE', self.setting_delete, apply=self.authentication(), name='api:setting_delete')

    bottle_app.route('/api/settings/profile_image/upload/', 'POST',   self.setting_upload_profile_image,   apply=self.authentication(), name='api:setting_upload_profile_image')
    bottle_app.route('/api/settings/',                      'PUT',    self.setting_update_multi,   apply=self.authentication(), name='api:setting_update_multi')
    bottle_app.route('/api/settings/',                      'GET',    self.setting_list,   apply=self.authentication(), name='api:setting_list')
    bottle_app.route('/api/settings/',                      'POST',   self.setting_add,    apply=self.authentication(), name='api:setting_add')

    # Status API
    bottle_app.route('/api/system_status/',                      'GET',    self.system_status,   apply=self.authentication(False), name='api:system_status')

    # Weather API
    bottle_app.route('/api/weather/',          'GET', self.weather_detail,   apply=self.authentication(False), name='api:weather')
    bottle_app.route('/api/weather/forecast/', 'GET', self.weather_forecast, apply=self.authentication(False), name='api:weather_forecast')

    # Webcam API
    bottle_app.route('/api/webcams/<webcam:path>/archive/<period:path>',      'GET',    self.webcam_archive, apply=self.authentication(False),      name='api:webcam_archive')
    bottle_app.route('/api/webcams/hardware/',      'GET',    self.webcam_hardware, apply=self.authentication(),      name='api:webcam_hardware')
    bottle_app.route('/api/webcams/<webcam:path>/', 'GET',    self.webcam_detail,   apply=self.authentication(False), name='api:webcam_detail')
    bottle_app.route('/api/webcams/<webcam:path>/', 'PUT',    self.webcam_update,   apply=self.authentication(),      name='api:webcam_update')
    bottle_app.route('/api/webcams/<webcam:path>/', 'DELETE', self.webcam_delete,   apply=self.authentication(),      name='api:webcam_delete')
    bottle_app.route('/api/webcams/',               'GET',    self.webcam_list,     apply=self.authentication(False), name='api:webcam_list')
    bottle_app.route('/api/webcams/',               'POST',   self.webcam_add,      apply=self.authentication(),      name='api:webcam_add')



    # API DOC
    bottle_app.route('/<page:re:(api/doc)>/',               'GET',   self.webserver.render_page,      apply=self.authentication(False),      name='api:documentation')
    bottle_app.route('/api/doc/swagger.json',   'GET',   self.api_spec,      apply=self.authentication(False),      name='api:swagger.json')


    #self.apispec.components.schema("AudioFile", schema=Audiofile)

#    self.apispec.path(view=self.audiofile_detail)
    self.apispec.path(view=self.audiofile_delete)
#    self.apispec.path(view=self.audiofile_list)
    self.apispec.path(view=self.audiofile_add)
    # print('TESTETSETESTE')

    # print(dir(orm))

    # print(orm.ormtypes)
    # print(dir(orm.ormtypes))

    # print(orm.show(Audiofile))
    # print(dir(orm))
#    with orm.db_session():
#      print(dir(Setting))
#      print(Setting['host'].to_dict())
#      print(Setting.to_json())

    # from pprint import pprint
    # print('APISPec test')
    # print(spec.path(view=self.webcam_list))

    # pprint(spec.to_dict())

#   def api_doc(self):
#     return jinja2_template(f'views/api.html')
# #    return self.apispec.to_dict()


  def api_spec(self):
#    return jinja2_template(f'views/{page.name}',**self.__template_variables(page_name))
    return self.apispec.to_dict()




  def _return_data(self, message, data):
    return {'message':message, 'data':data}

  # Areas
  def area_types(self):
    return { 'data' : terrariumArea.available_areas }

  @orm.db_session
  def area_list(self):
    data = []
    for area in Area.select(lambda r: not r.id in self.webserver.engine.settings['exclude_ids']):
      area_data = area.to_dict(exclude='enclosure')
      #area_data['value']  = area.value
      area_data['id']  = str(area.id)
      data.append(area_data)

    return { 'data' : data }

  @orm.db_session
  def area_detail(self, area):
    try:
      area = Area[area]
      area_data = area.to_dict(exclude='enclosure')
      area_data['id']  = str(area.id)
      return area_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Area with id {area} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting area {area} detail. {ex}')

  @orm.db_session
  def area_add(self):
    try:

      new_area = self.webserver.engine.add(terrariumArea(None, request.json['enclosure'], request.json['type'], request.json['name'], request.json['mode'], request.json['setup']))
      request.json['id']      = new_area.id
      #request.json['address'] = new_area.address

      area = Area(**request.json)

      return self.area_detail(str(area.pk))
      #new_value = new_area.update()
      #area.update(new_value)

      # area_data = area.to_dict(exclude='enclosure')
      # area_data['id']  = str(area.id)
      # #area_data['value']  = area.value
      # return area_data
    except Exception as ex:
      raise HTTPError(status=500, body=f'Area could not be added. {ex}')

  @orm.db_session
  def area_update(self, area):
    try:
      area = Area[area]

      area.set(**request.json)
      #self.webserver.engine.update(terrariumArea,**request.json)

      #area_data = area.to_dict(exclude='enclosure')
      #area_data['id']  = str(area.id)
      #area_data['value']  = area.value
      return self.area_detail(str(area.id))

      #return self._return_data(f'Update for \'{area}\' succeeded.',self.area_detail(str(area.pk))))
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Area with id {area} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error updating area {area}. {ex}')

  @orm.db_session
  def area_delete(self, area):
    try:
      message = f'Area {Area[area]} is deleted.'
      Area[area].delete()
#      self.webserver.engine.delete(terrariumArea,area)
      return {'message' : message}
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Area with id {area} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error deleting area {area}. {ex}')




  # Audiofiles
  @orm.db_session
  def audiofile_list(self):
    """Audio files list view.
    ---
    get:
      parameters:
      responses:
        200:
          content:
            application/json:
              schema: GistSchema
    """

    data = []
    for audiofile in Audiofile.select():
      data.append(audiofile.to_dict())

    return { 'data' : data }

  @orm.db_session
  def audiofile_detail(self, audiofile):
    """Audio file detail view.
    ---
    get:
      parameters:
      - in: audiofile
        schema: GistParameter
      responses:
        200:
          content:
            application/json:
              schema: GistSchema
    """
    try:
      audiofile = Audiofile[audiofile]
      audiofile_data = audiofile.to_dict()
      return audiofile_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Audiofile with id {audiofile} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting audiofile {audiofile} detail. {ex}')

#  @orm.db_session
  def audiofile_add(self):
    __UPLOAD_PATH = 'media/'
    data = []
    try:
      for upload in request.files.getlist('audiofiles'):
        upload.save(__UPLOAD_PATH, overwrite=True)
        meta_data = TinyTag.get(f'{__UPLOAD_PATH}{upload.filename}')

        item = {
          'id'       : md5(f'{upload.filename}'.encode()).hexdigest(),
          'name'     : f'{meta_data.title} - {meta_data.artist}',
          'filename' : f'{upload.filename}',
          'duration' : meta_data.duration,
          'filesize' : meta_data.filesize
        }

        try:
          with orm.db_session:
            audiofile = Audiofile(**item)
        except orm.core.TransactionIntegrityError as e:
          if 'UNIQUE constraint failed' in str(e):
            with orm.db_session:
              audiofile = Audiofile[item['id']]
              audiofile.set(**item)

        data.append(item)

      return {'data' : data}
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting audiofile {audiofile} detail. {ex}')


  @orm.db_session
  def audiofile_delete(self, audiofile):
    __UPLOAD_PATH = 'media/'
    try:
      audiofile = Audiofile[audiofile]
      message = f'Audio file {audiofile.filename} is deleted.'
      audio_file = Path(f'{__UPLOAD_PATH}{audiofile.filename}')
      if audio_file.exists():
        audio_file.unlink()
      audiofile.delete()
      return {'message' : message}
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Audiofile with id {audiofile} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error deleting audiofile {audiofile}. {ex}')


  # Buttons
  @orm.db_session
  def button_history(self, button, period = 'day'):
    data = []

    if 'day' == period:
      period = 1
    elif 'week' == period:
      period = 7
    elif 'month' == period:
      period = 31
    elif 'year' == period:
      period = 365
    else:
      period = 1

    for item in Button[button].history.filter(lambda h: h.timestamp >= datetime.now() - timedelta(days=period)):
      data.append({
        'timestamp' : item.timestamp.timestamp(),
        'value'     : item.value,
      })

    return { 'data' : data }

  def button_hardware(self):
    return { 'data' : terrariumButton.available_buttons }

  @orm.db_session
  def button_list(self):
    data = []
    for button in Button.select(lambda r: not r.id in self.webserver.engine.settings['exclude_ids']):
      button_data = button.to_dict(exclude='enclosure')
      button_data['value']  = button.value
      data.append(button_data)

    return { 'data' : data }

  @orm.db_session
  def button_detail(self, button):
    try:
      button = Button[button]
      button_data = button.to_dict(exclude='enclosure')
      button_data['value']  = button.value
      return button_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Button with id {button} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting button {button} detail. {ex}')

  @orm.db_session
  def button_add(self):
    try:
      new_button = self.webserver.engine.add(terrariumButton(None, request.json['hardware'], request.json['address'], request.json['name']))
      request.json['id']      = new_button.id
      request.json['address'] = new_button.address

      button = Button(**request.json)
      new_value = new_button.update()
      button.update(new_value)

      button_data = button.to_dict(exclude='enclosure')
      button_data['value']  = button.value
      return button_data
    except Exception as ex:
      raise HTTPError(status=500, body=f'Button could not be added. {ex}')

  @orm.db_session
  def button_update(self, button):
    try:
      button = Button[button]
      button.set(**request.json)
      self.webserver.engine.update(terrariumButton,**request.json)

      button_data = button.to_dict(exclude='enclosure')
      button_data['value']  = button.value
      return button_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Button with id {button} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error updating button {button}. {ex}')

  @orm.db_session
  def button_delete(self, button):
    try:
      message = f'Button {Button[button]} is deleted.'
      Button[button].delete()
      self.webserver.engine.delete(terrariumButton,button)
      return {'message' : message}
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Button with id {button} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error deleting button {button}. {ex}')


  # Calendar
  def calendar_detail(self,calendar):
    try:
      data = self.webserver.engine.calendar.get_event(calendar)
      if not data:
        # TODO: Make raising a CalendarNotFound exception
        raise HTTPError(status=404, body=f'Calender with id {calendar} does not exists.')

      return data
    except Exception as ex:
      raise HTTPError(status=404, body=f'Calender with id {calendar} does not exists.')

  def calendar_delete(self, calendar):
    data = self.calendar_detail(calendar)
    if not self.webserver.engine.calendar.delete_event(data['uid']):
      raise HTTPError(status=500, body=f'Calender event {data["summary"]} could not be removed.')

    return {'message' : f'Calender event {data["summary"]} is deleted.'}

  def calendar_update(self, calendar):
    data = data = self.calendar_detail(calendar)
    for field in request.json:

      if field in ['dtstart','dtend'] and request.json[field]:
        data[field] = datetime.fromtimestamp(int(request.json[field])).replace(tzinfo=timezone.utc)
      else:
        data[field] = request.json[field]

    event = self.webserver.engine.calendar.create_event(
      data['uid'],
      data['summary'],
      data['description'],
      data.get('location'),
      data['dtstart'],
      data['dtend'],

      data.get('freq'),
      data.get('interval')
    )

    return event

  def calendar_list(self, upcoming = False):
    start = request.query.get('start', None)
    if start:
      start = datetime.fromisoformat(start)

    end = request.query.get('end', None)
    if end:
      end = datetime.fromisoformat(end)

    output = []
    for event in self.webserver.engine.calendar.get_events(start,end):
      output.append({
        'id'          : event['uid'],
        'title'       : event['summary'],
        'description' : event['description'],
        'start'       : datetime.fromtimestamp(event['dtstart'],timezone.utc).strftime('%Y-%m-%d'),
        'end'         : datetime.fromtimestamp(event['dtend'],timezone.utc).strftime('%Y-%m-%d'),
      })

    # https://stackoverflow.com/a/12294213
    response.content_type = 'application/json'
    return dumps(output)

  def calendar_add(self):
    event = self.webserver.engine.calendar.create_event(
      None,
      request.json['summary'],
      request.json['description'],
      request.json.get('location'),
      datetime.fromtimestamp(int(request.json['dtstart'])).replace(tzinfo=timezone.utc),
      None if request.json['dtend'] is None else datetime.fromtimestamp(int(request.json['dtend'])).replace(tzinfo=timezone.utc),
      request.json['freq'],
      request.json['interval']
    )

    return event

  def calendar_download(self):
    icalfile = Path(self.webserver.engine.calendar.get_file())
    return static_file(icalfile.name, root='', download=icalfile.name)


  # Enclosure
  @orm.db_session
  def enclosure_list(self):
    data = []
    for enclosure in Enclosure.select(lambda e: not e.id in self.webserver.engine.settings['exclude_ids']):
      data.append(self.enclosure_detail(enclosure.id))

    return { 'data' : data }

  @orm.db_session
  def enclosure_detail(self, enclosure):
    try:
      enclosure = Enclosure[enclosure]
      enclosure_data = enclosure.to_dict(with_collections=True, related_objects=True)
      enclosure_data['id']  = str(enclosure.id)

      for area in list(enclosure_data['areas']):
        enclosure_data['areas'].remove(area)

        area = area.to_dict(exclude='enclosure')
        area['id'] = str(area['id'])

        enclosure_data['areas'].append(area)

      for door in list(enclosure_data['doors']):
        enclosure_data['doors'].remove(door)

        door_data = door.to_dict(exclude='enclosure')
        door_data['value'] = door.value

        enclosure_data['doors'].append(door_data)


      for webcam in list(enclosure_data['webcams']):
        enclosure_data['webcams'].remove(webcam)

        webcam_data = webcam.to_dict(exclude='enclosure')

        enclosure_data['webcams'].append(webcam_data)

      return enclosure_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Enclosure with id {enclosure} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting enclosure {enclosure} detail. {ex}')

  @orm.db_session
  def enclosure_add(self):
    try:
      doors_set = Button.select(lambda b: b.id in request.json['doors'])
      request.json['doors'] = doors_set

      webcams_set = Webcam.select(lambda w: w.id in request.json['webcams'])
      request.json['webcams'] = webcams_set
      enclosure = Enclosure(**request.json)

      # TODO: Fix this? We can't new enclosures without a restart .... :(
      #self.webserver.engine.add(terrariumEnclosure)

      return self.enclosure_detail(enclosure.id)

    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Door with id {request.json["doors"]} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Enclosure could not be added. {ex}')

  @orm.db_session
  def enclosure_update(self, enclosure):
    try:
      enclosure = Enclosure[enclosure]

      print('Update enclosure data to the engine')
      # TODO: Will this work... not sure....
      self.webserver.engine.update(terrariumEnclosure,**request.json)

      doors_set = Button.select(lambda b: b.id in request.json['doors'])
      request.json['doors'] = doors_set

      webcams_set = Webcam.select(lambda w: w.id in request.json['webcams'])
      request.json['webcams'] = webcams_set

      enclosure.set(**request.json)

      # print('Update enclosure data to the engine')
      # # TODO: Will this work... not sure....
      # self.webserver.engine.update(terrariumEnclosure,**request.json)

   #   enclosure_data = enclosure.to_dict(with_collections=True)
    #  enclosure_data['id']  = str(enclosure.id)
 #     enclosure_data['value']  = enclosure.value
      return self.enclosure_detail(enclosure.id)
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Enclosure with id {enclosure} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error updating enclosure {enclosure}. {ex}')

  @orm.db_session
  def enclosure_delete(self, enclosure):
    try:
      message = f'Enclosure {Enclosure[enclosure]} is deleted.'
      Enclosure[enclosure].delete()
 #     self.webserver.engine.delete(terrariumEnclosure,enclosure)
      return {'message' : message}
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Enclosure with id {enclosure} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error deleting enclosure {enclosure}. {ex}')




  # Logfile
  def logfile_download(self):
    # https://stackoverflow.com/a/26017181
    logfile = Path(terrariumLogging.logging.getLogger().handlers[1].baseFilename)
    return static_file(logfile.name, root='log', mimetype='text/text', download=logfile.name)


  # Reboot/start API
  def server_action(self, action):
    if 'restart' == action:
      ok = self.webserver.engine.restart()
      return { 'message' : f'TerrariumPI {self.webserver.engine.settings["version"]} is being restarted!' }
    elif 'reboot' == action:
      ok = self.webserver.engine.reboot()
      return { 'message' : f'TerrariumPI {self.webserver.engine.settings["version"]} is being rebooted!' }
    elif 'shutdow' == action:
      ok = self.webserver.engine.shutdown()
      return { 'message' : f'TerrariumPI {self.webserver.engine.settings["version"]} is being shutdown!' }


  # Relays
  @orm.db_session
  def relay_action(self, relay, action = 'toggle'):
    try:
      relay = Relay[relay]
      self.webserver.engine.toggle_relay(relay,action)

      relay_data = relay.to_dict()
      relay_data['value']  = relay.value
      relay_data['dimmer'] = relay.is_dimmer
      return relay_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Relay with id {relay} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting relay {relay} detail. {ex}')

  @orm.db_session
  def relay_manual(self, relay):
    try:
      relay = Relay[relay]
      relay.manual_mode = not relay.manual_mode

      relay_data = relay.to_dict()
      relay_data['value']  = relay.value
      relay_data['dimmer'] = relay.is_dimmer
      return relay_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Relay with id {relay} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error updating manual mode on relay {relay} detail. {ex}')

    pass

  @orm.db_session
  def relay_history(self, relay, action = 'history', period = 'day'):
    try:
      relay = Relay[relay]

      data = []

      if 'day' == period:
        period = 1
      elif 'week' == period:
        period = 7
      elif 'month' == period:
        period = 31
      elif 'year' == period:
        period = 365
      else:
        period = 1

      for item in relay.history.filter(lambda h: h.timestamp >= datetime.now() - timedelta(days=period)):
        data.append({
          'timestamp' : item.timestamp.timestamp(),
          'value'     : item.value,
          'wattage'   : item.wattage,
          'flow'      : item.flow
        })

      if 'export' == action:
        response.headers['Content-Type'] = 'application/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={relay.name}_{period}.csv'

        # CSV Headers
        csv_data = ';'.join(data[0].keys()) + '\n'
        # Data
        for data_point in data:
          data_point['timestamp'] = datetime.fromtimestamp(data_point['timestamp'])
          csv_data += ';'.join([str(value) for value in data_point.values()]) + '\n'

        return csv_data

      return { 'data' : data }

    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Relay with id {relay} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'{ex}')

  def relay_hardware(self):
    return { 'data' : terrariumRelay.available_relays }

  @orm.db_session
  def relay_list(self):
    data = []
    for relay in Relay.select(lambda r: not r.id in self.webserver.engine.settings['exclude_ids']):
      relay_data = relay.to_dict()
      relay_data['value']  = relay.value
      relay_data['dimmer'] = relay.is_dimmer
      data.append(relay_data)

    return { 'data' : data }

  @orm.db_session
  def relay_detail(self, relay):
    try:
      relay = Relay[relay]
      relay_data = relay.to_dict()
      relay_data['value']  = relay.value
      relay_data['dimmer'] = relay.is_dimmer
      return relay_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Relay with id {relay} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting relay {relay} detail. {ex}')

  @orm.db_session
  def relay_add(self):
    try:
      new_relay = self.webserver.engine.add(terrariumRelay(None, request.json['hardware'], request.json['address'], request.json['name']))
      if new_relay.is_dimmer:
        new_relay.calibrate(request.json['calibration'])

        #new_relay.set_freqency(request.json['calibration']['dimmer_freqency'])

      request.json['id']      = new_relay.id
      request.json['address'] = new_relay.address

      relay = Relay(**request.json)
      new_value = new_relay.update()
      relay.update(new_value)

      relay_data = relay.to_dict()
      relay_data['value']  = relay.value
      relay_data['dimmer'] = relay.is_dimmer
      return relay_data
    except Exception as ex:
      raise HTTPError(status=500, body=f'Relay could not be added. {ex}')

  @orm.db_session
  def relay_update(self, relay):
    try:
      relay = Relay[relay]
      relay.set(**request.json)
      self.webserver.engine.update(terrariumRelay,**request.json)

      relay_data = relay.to_dict()
      relay_data['value']  = relay.value
      relay_data['dimmer'] = relay.is_dimmer
      return relay_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Relay with id {relay} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error updating relay {relay}. {ex}')

  @orm.db_session
  def relay_delete(self, relay):
    try:
      message = f'Relay {Relay[relay]} is deleted.'
      Relay[relay].delete()
      self.webserver.engine.delete(terrariumRelay,relay)
      return {'message' : message}
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Relay with id {relay} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error deleting relay {relay}. {ex}')


  # Sensors
  @orm.db_session
  def sensor_history(self, filter = None, action = 'history', period = 'day'):
    data = []

    if 'day' == period:
      period = 1
    elif 'week' == period:
      period = 7
    elif 'month' == period:
      period = 31
    elif 'year' == period:
      period = 365
    else:
      period = 1

    if filter in terrariumSensor.sensor_types:
      query = orm.select((sh.timestamp,
                          orm.avg(sh.value),
                          orm.avg(sh.alarm_min),
                          orm.avg(sh.alarm_max)) for sh in SensorHistory if sh.sensor.type == filter and sh.timestamp >= datetime.now() - timedelta(days=period))

    else:
      query = orm.select((sh.timestamp,
                          sh.value,
                          sh.alarm_min,
                          sh.alarm_max,
                          sh.limit_min,
                          sh.limit_max)          for sh in SensorHistory if sh.sensor.id == filter   and sh.timestamp >= datetime.now() - timedelta(days=period))

    for item in query:
      data_point = {
        'timestamp' : item[0].timestamp(),
        'value'     : item[1],
        'alarm_min' : item[2],
        'alarm_max' : item[3]
      }
      if 'export' == action:
        data_point['limit_min'] = item[4]
        data_point['limit_max'] = item[5]
        data_point['alarm'] = not data_point['alarm_min'] <= data_point['value'] <= data_point['alarm_max']

      data.append(data_point)

    if 'export' == action:
      sensor = Sensor[filter]
      response.headers['Content-Type'] = 'application/csv'
      response.headers['Content-Disposition'] = f'attachment; filename={sensor.name}_{period}.csv'

      # CSV Headers
      csv_data = ';'.join(data[0].keys()) + '\n'
      # Data
      for data_point in data:
        data_point['timestamp'] = datetime.fromtimestamp(data_point['timestamp'])
        csv_data += ';'.join([str(value) for value in data_point.values()]) + '\n'

      return csv_data

    else:
      return { 'data' : data }

  def sensor_hardware(self):
    return { 'data' : terrariumSensor.available_sensors }

  @orm.db_session
  def sensor_list(self, filter = None):
    data = []
    for sensor in Sensor.select(lambda s: not s.id in self.webserver.engine.settings['exclude_ids']):
      if filter is None or filter == sensor.type:
        # TODO: Fix this that this can be done in a single query
        sensor_data = sensor.to_dict()
        sensor_data['value']  = sensor.value
        sensor_data['alarm']  = sensor.alarm
        sensor_data['error']  = sensor.error

        data.append(sensor_data)

    return { 'data' : data }

  @orm.db_session
  def sensor_detail(self, sensor):
    try:
      sensor = Sensor[sensor]
      sensor_data = sensor.to_dict()
      sensor_data['value']  = sensor.value
      sensor_data['alarm']  = sensor.alarm
      sensor_data['error']  = sensor.error
      return sensor_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Sensor with id {sensor} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting sensor {sensor} detail. {ex}')

  @orm.db_session
  def sensor_add(self):
    try:
      # Try to add a new sensor to the system
      new_sensor = self.webserver.engine.add(terrariumSensor(None, request.json['hardware'], request.json['type'], request.json['address'], request.json['name']))
      if 'chirp' == new_sensor.hardware.lower():
        # We need some moisture calibration for a Chirp sensor
        new_sensor.calibrate(request.json['calibration'])

      # The sensor will create a unique ID and can update the address
      request.json['id']      = new_sensor.id
      request.json['address'] = new_sensor.address

      sensor = Sensor(**request.json)
      new_value = new_sensor.update()
      sensor.update(new_value)

      self.webserver.websocket_message('sensortypes', self.webserver.engine.sensor_types_loaded)

      sensor_data = sensor.to_dict()
      sensor_data['value'] = sensor.value
      sensor_data['alarm'] = sensor.alarm
      sensor_data['error'] = sensor.error
      return sensor_data
    except Exception as ex:
      raise HTTPError(status=500, body=f'Sensor could not be added. {ex}')

  @orm.db_session
  def sensor_update(self, sensor):
    try:
      sensor = Sensor[sensor]
      sensor.set(**request.json)
      self.webserver.engine.update(terrariumSensor,**request.json)
      if 'chirp' == sensor.hardware.lower():
        # We need some moisture calibration for a Chirp sensor
        # TODO: This is a bad hack.....
        self.webserver.engine.sensors[sensor.id].calibrate(request.json['calibration'])

      sensor_data = sensor.to_dict()
      sensor_data['value'] = sensor.value
      sensor_data['alarm'] = sensor.alarm
      sensor_data['error'] = sensor.error

      return sensor_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Sensor with id {sensor} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error updating sensor {sensor}. {ex}')

  @orm.db_session
  def sensor_delete(self, sensor):
    try:
      message = f'Sensor {Sensor[sensor]} is deleted.'
      Sensor[sensor].delete()
      self.webserver.engine.delete(terrariumSensor,sensor)
      return {'message' : message}
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Sensor with id {sensor} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error deleting sensor {sensor}. {ex}')


  # Settings
  def setting_upload_profile_image(self):
    __UPLOAD_PATH = 'media/'
    data = []
    try:
      profile_image = request.files.get('file',None)
      if profile_image is not None:
        print(f'current filename: {profile_image.filename}')
        # Rename
        profile_image.filename = 'profile_image.jpg'
        profile_image.save(__UPLOAD_PATH, overwrite=True)

        return {'profile_image' : f'{__UPLOAD_PATH}{profile_image.filename}'}

    except Exception as ex:
      raise HTTPError(status=500, body=f'Error uploading profile image. {ex}')


    pass


  @orm.db_session
  def setting_list(self):
    settings = []
    for setting in Setting.select():
      # Never give out this value in a list
      if setting.id in ['password', 'meross_cloud_password']:
        continue
      settings.append(setting.to_dict())

    return { 'data' : settings }

  @orm.db_session
  def setting_detail(self, setting):
    try:
      return Setting[setting].to_dict()
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Setting with id {setting} does not exists.')

    raise HTTPError(status=500, body=f'Error processing setting {setting}.')

  @orm.db_session
  def setting_add(self):
    try:
      if 'password' == request.json['id']:
        request.json['value'] = terrariumUtils.generate_password(request.json['value'])

      setting = Setting(**request.json)
      self.webserver.engine.load_settings()
      return setting.to_dict()
    except Exception as ex:
      raise HTTPError(status=400, body=f'Error adding new setting. {ex}')

  @orm.db_session
  def setting_update(self, setting):
    try:
      data = Setting[setting]
      if 'exclude_ids' == data.id:
        tmp = data.value.strip(', ').split(',')
        if request.json['value'] in tmp:
          tmp.remove(request.json['value'])
        else:
          tmp.append(request.json['value'])

        request.json['value'] = ','.join(sorted(list(set(tmp)))).strip(', ')
      elif 'password' == data.id:
        request.json['value'] = terrariumUtils.generate_password(request.json['value'])

      data.set(**request.json)
      self.webserver.engine.load_settings()
      return data.to_dict()
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Setting with id {setting} does not exists.')
    except Exception as ex:
      raise HTTPError(status=400, body=f'Error updating new setting {setting}. {ex}')

  @orm.db_session
  def setting_update_multi(self):
    # First check if new password is set and is entered twice:
    if '' != request.json['password'] and request.json['password'] != request.json['password2']:
      raise HTTPError(status=400, body=f'Password fields do not match.')

    # Delete the confirmation password
    del(request.json['password2'])
    # Delete normal password when empty so we keep the old one
    if '' == request.json['password']:
      del(request.json['password'])

    for key in request.json.keys():
      try:
        setting = Setting[key]
        if 'password' == key:
          setting.value = terrariumUtils.generate_password(request.json[key])
        else:
          setting.value = request.json[key]

        orm.commit()

      except orm.core.ObjectNotFound as ex:
        # Non existing setting can be ignored
        pass

    self.webserver.engine.load_settings()
    return {'status' : True}

  @orm.db_session
  def setting_delete(self, setting):
    try:
      Setting[setting].delete()
      return {'message' : f'Setting id {setting} is deleted.'}
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Setting with id {setting} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Setting {setting} could not be removed. {ex}')


  # System
  def system_status(self):
    return self.webserver.engine.system_stats()


  # Weather
  def weather_detail(self):
    if not self.webserver.engine.weather:
      raise HTTPError(status=404, body=f'No weather data available.')

    weather = {
      'location'   : self.webserver.engine.weather.location,
      'sun'        : {'rise' :self.webserver.engine.weather.sunrise.timestamp(), 'set' : self.webserver.engine.weather.sunset.timestamp() },
      'is_day'     : self.webserver.engine.weather.is_day,
      'indicators' : {'wind' : 'km/h', 'temperature' : '°C'},
      'credits'    : self.webserver.engine.weather.credits,
      'forecast'   : self.webserver.engine.weather._data['days']
    }

    return weather

  def weather_forecast(self):
    if not self.webserver.engine.weather:
      raise HTTPError(status=404, body=f'No weather data available.')

    data = []
    for forecast_item in self.webserver.engine.weather.forecast:
      forecast = copy.copy(forecast_item)
      forecast['timestamp'] = forecast['timestamp'].timestamp()
      data.append(forecast)

    return {'data' : data}


  # Webcams
  def webcam_hardware(self):
    return { 'data' : terrariumWebcam.available_webcams }

  @orm.db_session
  def webcam_archive(self, webcam, period = None):
    try:
      webcam = Webcam[webcam]
      webcam_data = webcam.to_dict(exclude='enclosure')
      webcam_data['is_live'] = webcam.is_live

      if period is None:
        period = datetime.now().strftime('%Y/%m/%d')

      archive_path = Path(webcam.archive_path) / period
      webcam_data['archive_images'] = [f'/{archive_file}' for archive_file in sorted(archive_path.glob('*.jpg'), reverse=True)]

      return webcam_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Webcam with id {webcam} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting webcam {webcam} archive images. {ex}')

  @orm.db_session
  def webcam_list(self):
    data = []
    for webcam in Webcam.select(lambda w: not w.id in self.webserver.engine.settings['exclude_ids']):
      webcam_data = webcam.to_dict(exclude='enclosure')
      webcam_data['is_live'] = webcam.is_live
      data.append(webcam_data)

    return { 'data' : data }

  @orm.db_session
  def webcam_detail(self, webcam):
    try:
      webcam = Webcam[webcam]
      webcam_data = webcam.to_dict(exclude='enclosure')
      webcam_data['is_live'] = webcam.is_live
      return webcam_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Webcam with id {webcam} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error getting webcam {webcam} detail. {ex}')

  @orm.db_session
  def webcam_add(self):
    try:
      new_webcam = self.webserver.engine.add(terrariumWebcam(None,
                                                             request.json['address'],
                                                             request.json['name'],
                                                             request.json['width'],
                                                             request.json['height'],
                                                             request.json['rotation'],
                                                             request.json['awb']))
      request.json['id']      = new_webcam.id
      request.json['address'] = new_webcam.address
      # After loading some remote webcams, we could have a different resolution then entered
      request.json['width']   = new_webcam.width
      request.json['height']  = new_webcam.height

      request.json['markers'] = json.loads(request.json['markers'])

      webcam = Webcam(**request.json)
      # TODO: Fix updating or not. For now, disabled, as it can take up to 12 sec for RPICam
      #new_value = new_webcam.update()

      webcam_data = webcam.to_dict(exclude='enclosure')
      webcam_data['is_live'] = webcam.is_live
      return webcam_data
    except Exception as ex:
      raise HTTPError(status=500, body=f'Webcam could not be added. {ex}')

  @orm.db_session
  def webcam_update(self, webcam):
    try:
      webcam = Webcam[webcam]

      request.json['markers'] = json.loads(request.json['markers'])

      webcam.set(**request.json)

      self.webserver.engine.update(terrariumWebcam,**request.json)

      webcam_data = webcam.to_dict(exclude='enclosure')
      webcam_data['is_live'] = webcam.is_live
      return webcam_data
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Webcam with id {webcam} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error updating webcam {webcam}. {ex}')

  @orm.db_session
  def webcam_delete(self, webcam):
    try:
      message = f'Webcam {Webcam[webcam]} is deleted.'
      Webcam[webcam].delete()
      self.webserver.engine.delete(terrariumWebcam,webcam)
      return message
    except orm.core.ObjectNotFound as ex:
      raise HTTPError(status=404, body=f'Webcam with id {webcam} does not exists.')
    except Exception as ex:
      raise HTTPError(status=500, body=f'Error deleting webcam {webcam}. {ex}')