from . import terrariumRelayDimmer

# pip install PCA9685-driver
# pip uninstall smbus-cffi
import pca9685_driver

class terrariumRelayDimmerPCA9685(terrariumRelayDimmer):
  HARDWARE = 'pca9685-dimmer'
  NAME = 'PCA9685-dimmer'

  # Dimmer settings
  _DIMMER_FREQ   = 1000
  _DIMMER_MAXDIM = 4095

  _DEFAULT_ADDRESS = '0x40'

  def _load_hardware(self):
    # address is expected as `[relay_number],[i2c_address]`
    address = self._address
    if len(address) == 1:
      address.append(self._DEFAULT_ADDRESS)

    if not address[1].startswith('0x'):
      address[1] = '0x' + address[1]

    self._device['switch'] = int(address[0])
    self._device['device'] = pca9685_driver.Device(int(address[1],16), None if len(address) != 3 else int(address[2]))
    self._device['device'].set_pwm_frequency(self._DIMMER_FREQ)

    return self._device['device']

  def _set_hardware_value(self, state):
    dim_value = int(self._DIMMER_MAXDIM * (float(state) / 100.0))
    self._device['device'].set_pwm(self._device['switch'], dim_value)
    return True

  def _get_hardware_value(self):
    return round((1.0 - float(self._device['device'].get_pwm(self._device['switch'])) / 1000.0 / self._DIMMER_MAXDIM) * 100.0)
