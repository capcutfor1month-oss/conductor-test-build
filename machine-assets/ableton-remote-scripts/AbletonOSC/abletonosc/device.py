from typing import Tuple, Any
from .handler import AbletonOSCHandler

class DeviceHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "device"

    def init_api(self):
        def create_device_callback(func, *args, include_ids: bool = False):
            def device_callback(params: Tuple[Any]):
                track_index, device_index = int(params[0]), int(params[1])
                device = self.song.tracks[track_index].devices[device_index]
                if (include_ids):
                    rv = func(device, *args, params[0:])
                else:
                    rv = func(device, *args, params[2:])

                if rv is not None:
                    return (track_index, device_index, *rv)

            return device_callback

        methods = [
        ]
        properties_r = [
            "class_name",
            "name",
            "type"
        ]
        properties_rw = [
            "is_active",
        ]

        for method in methods:
            self.osc_server.add_handler("/live/device/%s" % method,
                                        create_device_callback(self._call_method, method))

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/device/get/%s" % prop,
                                        create_device_callback(self._get_property, prop))
            self.osc_server.add_handler("/live/device/start_listen/%s" % prop,
                                        create_device_callback(self._start_listen, prop))
            self.osc_server.add_handler("/live/device/stop_listen/%s" % prop,
                                        create_device_callback(self._stop_listen, prop))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/device/set/%s" % prop,
                                        create_device_callback(self._set_property, prop))

        #--------------------------------------------------------------------------------
        # Device: Get/set parameter lists
        #--------------------------------------------------------------------------------
        def device_get_num_parameters(device, params: Tuple[Any] = ()):
            return len(device.parameters),

        def device_get_parameters_name(device, params: Tuple[Any] = ()):
            return tuple(parameter.name for parameter in device.parameters)

        def device_get_parameters_value(device, params: Tuple[Any] = ()):
            return tuple(parameter.value for parameter in device.parameters)

        def device_get_parameters_min(device, params: Tuple[Any] = ()):
            return tuple(parameter.min for parameter in device.parameters)

        def device_get_parameters_max(device, params: Tuple[Any] = ()):
            return tuple(parameter.max for parameter in device.parameters)

        def device_get_parameters_is_quantized(device, params: Tuple[Any] = ()):
            return tuple(parameter.is_quantized for parameter in device.parameters)

        def device_set_parameters_value(device, params: Tuple[Any] = ()):
            for index, value in enumerate(params):
                device.parameters[index].value = value

        self.osc_server.add_handler("/live/device/get/num_parameters", create_device_callback(device_get_num_parameters))
        self.osc_server.add_handler("/live/device/get/parameters/name", create_device_callback(device_get_parameters_name))
        self.osc_server.add_handler("/live/device/get/parameters/value", create_device_callback(device_get_parameters_value))
        self.osc_server.add_handler("/live/device/get/parameters/min", create_device_callback(device_get_parameters_min))
        self.osc_server.add_handler("/live/device/get/parameters/max", create_device_callback(device_get_parameters_max))
        self.osc_server.add_handler("/live/device/get/parameters/is_quantized", create_device_callback(device_get_parameters_is_quantized))
        self.osc_server.add_handler("/live/device/set/parameters/value", create_device_callback(device_set_parameters_value))

        #--------------------------------------------------------------------------------
        # Device: Get/set individual parameters
        #--------------------------------------------------------------------------------
        def device_get_parameter_value(device, params: Tuple[Any] = ()):
            # Cast to ints so that we can tolerate floats from interfaces such as TouchOSC
            # that send floats by default.
            # https://github.com/ideoforms/AbletonOSC/issues/33
            param_index = int(params[0])
            return param_index, device.parameters[param_index].value
        
        # Uses str_for_value method to return the UI-friendly version of a parameter value (ex: "2500 Hz")
        def device_get_parameter_value_string(device, params: Tuple[Any] = ()):
            param_index = int(params[0])
            return param_index, device.parameters[param_index].str_for_value(device.parameters[param_index].value)
        
        def device_get_parameter_value_listener(device, params: Tuple[Any] = ()):

            def property_changed_callback():
                value = device.parameters[params[2]].value
                self.logger.info("Property %s changed of %s %s: %s" % ('value', 'device parameter', str(params), value))
                self.osc_server.send("/live/device/get/parameter/value", (*params, value,))

                value_string = device.parameters[params[2]].str_for_value(device.parameters[params[2]].value)
                self.logger.info("Property %s changed of %s %s: %s" % ('value_string', 'device parameter', str(params), value_string))
                self.osc_server.send("/live/device/get/parameter/value_string", (*params, value_string,))

            listener_key = ('device_parameter_value', tuple(params))
            if listener_key in self.listener_functions:
               device_get_parameter_remove_value_listener(device, params)

            self.logger.info("Adding listener for %s %s, property: %s" % ('device parameter', str(params), 'value'))
            device.parameters[params[2]].add_value_listener(property_changed_callback)
            self.listener_functions[listener_key] = property_changed_callback

            property_changed_callback()

        def device_get_parameter_remove_value_listener(device, params: Tuple[Any] = ()):
            listener_key = ('device_parameter_value', tuple(params))
            if listener_key in self.listener_functions:
                self.logger.info("Removing listener for %s %s, property %s" % (self.class_identifier, str(params), 'value'))
                listener_function = self.listener_functions[listener_key]
                device.parameters[params[2]].remove_value_listener(listener_function)
                del self.listener_functions[listener_key]
            else:
                self.logger.warning("No listener function found for property: %s (%s)" % (prop, str(params)))

        def device_set_parameter_value(device, params: Tuple[Any] = ()):
            param_index, param_value = params[:2]
            param_index = int(param_index)
            device.parameters[param_index].value = param_value

        def device_get_parameter_name(device, params: Tuple[Any] = ()):
            param_index = int(params[0])
            return param_index, device.parameters[param_index].name

        def device_get_parameter_display_value(device, params: Tuple[Any] = ()):
            param_index = int(params[0])
            return param_index, device.parameters[param_index].str_for_value(device.parameters[param_index].value)

        def device_get_parameter_min(device, params: Tuple[Any] = ()):
            param_index = int(params[0])
            return param_index, device.parameters[param_index].min

        def device_get_parameter_max(device, params: Tuple[Any] = ()):
            param_index = int(params[0])
            return param_index, device.parameters[param_index].max

        self.osc_server.add_handler("/live/device/get/parameter/value", create_device_callback(device_get_parameter_value))
        self.osc_server.add_handler("/live/device/get/parameter/value_string", create_device_callback(device_get_parameter_value_string))
        self.osc_server.add_handler("/live/device/get/parameter/display_value", create_device_callback(device_get_parameter_display_value))
        self.osc_server.add_handler("/live/device/get/parameter/min", create_device_callback(device_get_parameter_min))
        self.osc_server.add_handler("/live/device/get/parameter/max", create_device_callback(device_get_parameter_max))
        self.osc_server.add_handler("/live/device/set/parameter/value", create_device_callback(device_set_parameter_value))
        self.osc_server.add_handler("/live/device/get/parameter/name", create_device_callback(device_get_parameter_name))
        self.osc_server.add_handler("/live/device/start_listen/parameter/value", create_device_callback(device_get_parameter_value_listener, include_ids = True))
        self.osc_server.add_handler("/live/device/stop_listen/parameter/value", create_device_callback(device_get_parameter_remove_value_listener, include_ids = True))

        #--------------------------------------------------------------------------------
        # Device: Load by name (browser search) and delete
        #--------------------------------------------------------------------------------
        def device_load(params: Tuple[Any] = ()):
            import Live
            track_index = int(params[0])
            device_name = str(params[1])

            application = Live.Application.get_application()
            browser = application.browser

            # Select the target track so load_item places the device there
            self.song.view.selected_track = self.song.tracks[track_index]

            def find_item(root, name_lower):
                try:
                    for item in root.children:
                        if hasattr(item, 'name') and item.name.lower() == name_lower:
                            return item
                        if item.is_folder:
                            result = find_item(item, name_lower)
                            if result:
                                return result
                except Exception:
                    pass
                return None

            name_lower = device_name.lower()
            found_item = None
            for category in [browser.audio_effects, browser.instruments, browser.midi_effects, browser.plugins]:
                try:
                    found_item = find_item(category, name_lower)
                    if found_item:
                        break
                except Exception:
                    continue

            if found_item:
                browser.load_item(found_item)
                return (1, found_item.name)
            else:
                return (0, "Device not found: " + device_name)

        def device_delete(params: Tuple[Any] = ()):
            track_index = int(params[0])
            device_index = int(params[1])
            self.song.tracks[track_index].delete_device(device_index)
            return (1,)

        self.osc_server.add_handler("/live/device/load", device_load)
        self.osc_server.add_handler("/live/device/delete", device_delete)
