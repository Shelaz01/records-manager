"""
wia_scan/core.py: an accumulation of helper functions
"""

import os
import tempfile
from datetime import datetime

import win32com.client
from PIL import Image as PILImage

# https://learn.microsoft.com/en-us/previous-versions/windows/desktop/wiaaut/-wiaaut-consts-misc
WIA_ID_UNKNOWN = '{00000000-0000-0000-0000-000000000000}'

# https://learn.microsoft.com/en-us/previous-versions/windows/desktop/wiaaut/-wiaaut-consts-formatid
WIA_FORMAT_BMP = '{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}'
WIA_FORMAT_PNG = '{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}'
WIA_FORMAT_GIF = '{B96B3CB0-0728-11D3-9D7B-0000F81EF32E}'
WIA_FORMAT_JPEG = '{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}'
WIA_FORMAT_TIFF = '{B96B3CB1-0728-11D3-9D7B-0000F81EF32E}'

# https://learn.microsoft.com/en-us/previous-versions/windows/desktop/wiaaut/-wiaaut-consts-commandid
WIA_COMMAND_SYNCHRONIZE = "{AF933CAC-ACAD-11D2-A093-00C04F72DC3C}"
WIA_COMMAND_TAKE_PICTURE = "{AF933CAC-ACAD-11D2-A093-00C04F72DC3C}"
WIA_COMMAND_DELETE_ALL_ITEMS = "{E208C170-ACAD-11D2-A093-00C04F72DC3C}"
WIA_COMMAND_CHANGE_DOCUMENT = "{04E725B0-ACAE-11D2-A093-00C04F72DC3C}"
WIA_COMMAND_UNLOAD_DOCUMENT = "{1F3B3D8E-ACAE-11D2-A093-00C04F72DC3C}"


WIA_EXTENSION_TO_FORMAT = {
    'bmp': WIA_FORMAT_BMP,
    'png': WIA_FORMAT_PNG,
    'gif': WIA_FORMAT_GIF,
    'jpeg': WIA_FORMAT_JPEG,
    'tiff': WIA_FORMAT_TIFF,
}


NOT_VERBOSE_PRINT_DEVICE_PROPERTIES = [
    'Unique Device ID', 'Manufacturer', 'Description', 'Server', 'Port', 'Name']


class IndentPrinter:
    """ A class to help with indentation of output """

    def __init__(self, indent, print_function):
        self.indent = indent
        self.print_function = print_function

    def __call__(self, *args, **kwargs):
        total_indent = self.indent + kwargs.get('indent', 0)

        args_as_string = " ".join([str(x) for x in args])
        output = ('  ' * total_indent) + args_as_string
        self.print_function(output)


DEFAULT_PRINT_FUNCTION = IndentPrinter(indent=0, print_function=print)


def print_device_properties(device, print_function=DEFAULT_PRINT_FUNCTION):
    print_function('Device Commands: ', indent=0)
    for command in device.Commands:
        print_function(f'{command.Name}: {command.Description}', indent=1)

    print_function('Device properties: ', indent=0)
    for property_ in device.Properties:
        readonly = ''
        if property_.IsReadOnly:
            readonly = '[Readonly]'
        print_function(
            f'{property_.Name}: {property_.Value} {readonly}', indent=1)
        if property_.Name in ['Format', 'Preferred Format']:
            print_function(
                f'Format extension: {format_id_to_extension(property_.Value)}', indent=2)


def press_any_key_to_continue():
    #os.system("pause")
    pass


def print_object_debug(name, obj, print_function=DEFAULT_PRINT_FUNCTION):
    print_function(name, ' ', type(obj))
    for property_ in dir(obj):
        print_function('obj.property_ ', property_, indent=1)
    print_function(obj)


def print_wia_image_debug(wia_image, print_function=DEFAULT_PRINT_FUNCTION):
    print_object_debug('image ', wia_image,
                       print_function=print_function)
    print_function('format id', wia_image.FormatID)
    print_function(
        'format name', format_id_to_extension(wia_image.FormatID))
    print_function('FrameCount id', wia_image.FrameCount)
    print_function('IsAlphaPixelFormat', wia_image.IsAlphaPixelFormat)
    print_function('IsExtendedPixelFormat',
                   wia_image.IsExtendedPixelFormat)
    print_function('IsIndexedPixelFormat',
                   wia_image.IsIndexedPixelFormat)
    print_function('PixelDepth', wia_image.PixelDepth)
    print_function('VerticalResolution', wia_image.VerticalResolution)
    print_function('Height', wia_image.Height)
    print_function('Width', wia_image.Width)


def format_id_to_extension(wia_id):
    for name, value in WIA_EXTENSION_TO_FORMAT.items():
        if value == wia_id:
            return name
    return 'UNKOWN_WIA_FORMAT'


def get_device_manager():
    """ Returns the wia device manager """
    device_manager = win32com.client.Dispatch("WIA.DeviceManager")
    return device_manager


def print_item_tree(item, print_function=DEFAULT_PRINT_FUNCTION):
    print_device_properties(item, print_function=print_function)
    more_indent_function = IndentPrinter(
        indent=1, print_function=print_function)
    for item_index in range(1, item.Items.Count + 1):
        print_function('sub item ', item_index)
        item_ = item.Items(item_index)
        print_item_tree(item_, print_function=more_indent_function)


def list_devices(device_manager, print_function=DEFAULT_PRINT_FUNCTION, verbose=False):
    """ Prints the available devices to print_function """

    if device_manager.DeviceInfos.Count == 0:
        print_function('No available device found', indent=0)
    else:
        print_function('Available Devices:', indent=0)
        for item_index in range(1, device_manager.DeviceInfos.Count + 1):
            device_info = device_manager.DeviceInfos(item_index)
            print_function(f'Device {item_index}', indent=0)
            for property_ in device_info.Properties:
                print_this_property = verbose or property_.Name in NOT_VERBOSE_PRINT_DEVICE_PROPERTIES
                if print_this_property:
                    print_function(
                        f'{property_.Name}: {property_.Value}', indent=1)


def ask_for_an_int(prompt_message, default, valid_range):
    while True:
        answer = input(f'{prompt_message} [Default: {default}]: ')
        if len(answer) == 0:
            answer = default
        try:
            value = int(answer)
            if value < valid_range[0] or value > valid_range[1]:
                print(
                    f'Answer outside of valid range, valid range is {valid_range}')
            else:
                return value
        except ValueError:
            print('Could not understand answer, please try again')


def prompt_choose_device(device_manager, print_function=DEFAULT_PRINT_FUNCTION, verbose=False):
    if device_manager.DeviceInfos.Count == 0:
        raise ValueError(
            "device must be available to choose, but none is available")

    print_function('Available Devices:', indent=0)
    device_ids = []
    for item_index in range(1, device_manager.DeviceInfos.Count + 1):
        device_info = device_manager.DeviceInfos(item_index)
        print_function(f'Device {item_index}', indent=0)
        for property_ in device_info.Properties:
            print_this_property = verbose or property_.Name in NOT_VERBOSE_PRINT_DEVICE_PROPERTIES
            if print_this_property:
                print_function(property_.Name, ' ', property_.Value, indent=2)
        device_ids.append(device_info.DeviceID)
    assert len(device_ids) == device_manager.DeviceInfos.Count, \
        'Require finding unique device ids, did not find them'

    index = ask_for_an_int('Choose a device number',
                           default=1, valid_range=(1, len(device_ids)))

    return device_ids[index - 1]


def get_device_info_by_unique_id(device_manager, unique_id):
    assert isinstance(unique_id, str)
    return device_manager.DeviceInfos(unique_id)


def get_scan_source(device, print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=False):
    if device.Items.Count == 1:
        device = device.Items(1)
    elif device.Items.Count == 0:
        pass
    else:
        raise NotImplementedError(
            'only one scan source is implemented at this point')

    assert device.Items.Count == 0
    if verbose:
        print_object_debug('device ', device,
                           print_function=print_function)
        print_device_properties(device, print_function=print_function)

    return device


def connect_device(device_manager, device_uid,
                   print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=False):
    if not device_uid:
        raise ValueError('device_uid is required when quiet')
    device_info = get_device_info_by_unique_id(
        device_manager, unique_id=device_uid)
    if device_info is None:
        raise ValueError(f'Could not find device with id {device_uid}')

    if not quiet:
        print_function('Connecting ... ')
    device = device_info.Connect()
    if not quiet:
        print_function('Connected ')

    if verbose:
        print_function('Printing item tree: ')
        print_item_tree(device, print_function=print_function)

    device = get_scan_source(
        device, print_function=print_function, verbose=verbose, quiet=quiet)

    return device


def connect_to_device_by_uid(
        device_uid, print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=False):
    device_manager = get_device_manager()
    device = connect_device(device_manager=device_manager, device_uid=device_uid,
                            print_function=print_function, verbose=verbose, quiet=quiet)
    return device


'''def prompt_choose_device_and_connect(
        print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=False):
    if quiet:
        raise ValueError(
            'cannot prompt choose device when quiet, device_uid is required when quiet')
    device_manager = get_device_manager()
    device_uid = prompt_choose_device(
        device_manager=device_manager, print_function=print_function, verbose=verbose)
    device = connect_device(device_manager=device_manager,
                            device_uid=device_uid, print_function=print_function,
                            verbose=verbose, quiet=quiet)
    return device


def scan_side(device, scan_profile=None, return_wia_image=False,
              print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=False):
    """
    Scans a single side and returns the WIA Image

    Parameters
    ----------
    device : wia device
        can be found by calling connect_device
    scan_profile : dict{
        'brightness': 0   Goes from -1000 to 1000
        'contrast': 0     Goes from -1000 to 1000
        'dpi': 200        Supported values depend on scanner
        'mode':  'RGB' for colored or 'L' for grayscale
    }

    """

    if scan_profile is None:
        scan_profile = get_default_profile()

    device.Properties('Brightness').Value = scan_profile['brightness']
    device.Properties('Contrast').Value = scan_profile['contrast']
    device.Properties('Horizontal Resolution').Value = scan_profile['dpi']
    device.Properties('Vertical Resolution').Value = scan_profile['dpi']
    if scan_profile['mode'] == 'RGB':
        device.Properties('Data Type').Value = 3
    elif scan_profile['mode'] == 'L':
        device.Properties('Data Type').Value = 2
    else:
        raise ValueError('unsupported mode')

    if not quiet:
        print_function('Scanning...')

    if verbose:
        print_device_properties(device, print_function=print_function)

        print_function('Available Transfer Formats')
        for format_ in device.Formats:
            print_function('Format ', format_, indent=1)

    # device.ExecuteCommand(WIA_COMMAND_TAKE_PICTURE) # this doesnt work for some wierd reason
    for command in device.Commands:
        if command.CommandID == WIA_COMMAND_TAKE_PICTURE:
            device.ExecuteCommand(WIA_COMMAND_TAKE_PICTURE)

    wia_image = device.Transfer(WIA_FORMAT_BMP)
    # if bmp is not supported as transfer format, wia will automatically choose the preferred method
    # https://learn.microsoft.com/en-us/previous-versions/windows/desktop/wiaaut/-wiaaut-iitem-transfer

    if not quiet:
        print_function('Done')

    if verbose:
        print_wia_image_debug(wia_image, print_function=print_function)

    if return_wia_image:
        return wia_image

    # to convert to a pillow image, we save it to disk, this is much faster on
    # most current platforms then reading the ARGB data from wia_image, as long as
    # we do not want to add numba or sth as a dependency

    tmp_directory = tempfile.mkdtemp()
    if verbose:
        print_function(f'Created temporary directory {tmp_directory}')
    tmp_file_name = os.path.join(tmp_directory, 'tmp.png')

    if verbose:
        print_function(f'Saving temporary image to {tmp_file_name}')

    wia_image.SaveFile(tmp_file_name)

    pillow_image_file = PILImage.open(tmp_file_name)
    pillow_image = pillow_image_file.copy()
    pillow_image_file.close()

    os.remove(tmp_file_name)
    os.rmdir(tmp_directory)

    return pillow_image'''

def prompt_choose_device_and_connect(print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=False):
    if quiet:
        raise ValueError('cannot prompt choose device when quiet, device_uid is required when quiet')
    device_manager = get_device_manager()
    devices = [device for device in device_manager.Devices]
    if not devices:
        return None
    device_uid = devices[0].DeviceID  # Automatically choose the first device
    device = connect_device(device_manager=device_manager, device_uid=device_uid, print_function=print_function, verbose=verbose, quiet=quiet)
    return device

def scan_side(device, scan_profile=None, return_wia_image=False, print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=False):
    if scan_profile is None:
        scan_profile = get_default_profile()

    device.Properties('Brightness').Value = scan_profile['brightness']
    device.Properties('Contrast').Value = scan_profile['contrast']
    device.Properties('Horizontal Resolution').Value = scan_profile['dpi']
    device.Properties('Vertical Resolution').Value = scan_profile['dpi']
    if scan_profile['mode'] == 'RGB':
        device.Properties('Data Type').Value = 3
    elif scan_profile['mode'] == 'L':
        device.Properties('Data Type').Value = 2
    else:
        raise ValueError('unsupported mode')

    if not quiet:
        print_function('Scanning...')

    if verbose:
        print_device_properties(device, print_function=print_function)
        print_function('Available Transfer Formats')
        for format_ in device.Formats:
            print_function('Format ', format_, indent=1)

    for command in device.Commands:
        if command.CommandID == WIA_COMMAND_TAKE_PICTURE:
            device.ExecuteCommand(WIA_COMMAND_TAKE_PICTURE)

    wia_image = device.Transfer(WIA_FORMAT_BMP)

    if not quiet:
        print_function('Done')

    if verbose:
        print_wia_image_debug(wia_image, print_function=print_function)

    if return_wia_image:
        return wia_image

    tmp_directory = tempfile.mkdtemp()
    if verbose:
        print_function(f'Created temporary directory {tmp_directory}')
    tmp_file_name = os.path.join(tmp_directory, 'tmp.png')

    if verbose:
        print_function(f'Saving temporary image to {tmp_file_name}')

    wia_image.SaveFile(tmp_file_name)

    pillow_image_file = PILImage.open(tmp_file_name)
    pillow_image = pillow_image_file.copy()
    pillow_image_file.close()

    os.remove(tmp_file_name)
    os.rmdir(tmp_directory)

    return pillow_image


def get_device_quiet_or_choose(device_uid, print_function, verbose, quiet):
    if not device_uid:
        device = prompt_choose_device_and_connect(
            print_function=print_function, verbose=verbose, quiet=quiet)
    else:
        device = connect_to_device_by_uid(
            device_uid, print_function=print_function, verbose=verbose, quiet=quiet)
    return device


def run_calibration_process(
        start_range, end_range, num_runs, device_uid, output_folder,
        print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=False):
    assert num_runs > 1

    if not quiet:
        print_function(
            'This calibration process consists of running a few scans')
        print_function(
            ' and you choosing yourself visually which setting is the best')
        press_any_key_to_continue()

    device = get_device_quiet_or_choose(
        device_uid=device_uid, print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=quiet)

    if not quiet:
        print_function(
            'Please put a calibration piece of paper in the scanner')
        print_function(
            'Consider something like a print of an it8 target (unrelated to this project)')
        press_any_key_to_continue()

    for i in range(num_runs):
        lam_ = i / float(num_runs - 1)
        brightness = (1.0 - lam_) * start_range + lam_ * end_range
        scan_profile = {
            'brightness': brightness,
            'contrast': 0,
            'dpi': 100,
            'mode': 'RGB'
        }

        pillow_image = scan_side(
            device=device,
            scan_profile=scan_profile,
            print_function=print_function,
            verbose=verbose,
            quiet=quiet)
        filepath = os.path.join(
            output_folder, f'run={i+1}_brightness={brightness}.jpg')
        pillow_image.save(filepath, subsampling=0,
                          optimize=True, progressive=True, quality=80)


def combine_images_vertically(image_list, mode):
    assert len(image_list) > 0
    if len(image_list) == 1:
        return image_list[0]

    combined_image_width = 0
    combined_image_height = 0
    for pillow_image in image_list:
        combined_image_width = max(combined_image_width, pillow_image.size[0])
        combined_image_height = combined_image_height + pillow_image.size[1]

    pillow_image_combined = PILImage.new(mode,
                                         (combined_image_width, combined_image_height))

    y_offset = 0
    for pillow_image in image_list:
        pillow_image_combined.paste(pillow_image, (0, y_offset))
        y_offset = y_offset + pillow_image.size[1]

    return pillow_image_combined


def save_image_list(image_list, filepath, profile):
    file_extension = filepath.split(os.extsep)[-1].lower()

    if file_extension in ['jpg', 'jpeg', 'png', 'bmp', 'tga', 'tiff']:
        pillow_image_combined = combine_images_vertically(image_list,
                                                          mode=profile['mode'])
        pillow_image_combined.save(filepath, subsampling=0, optimize=True,
                                   progressive=True, quality=profile['jpeg_quality'])
    elif file_extension == 'pdf':
        image_list[0].save(filepath, save_all=True, append_images=image_list[1:],
                           resolution=profile['dpi'], subsampling=0, optimize=True,
                           progressive=True, quality=profile['jpeg_quality'])
    else:
        raise ValueError("unexpected extension")


def get_profiles():
    profiles = {
        'm': {
            'name': 'Medium Quality',
            'file_extension': 'png',
            'mode': 'RGB',
            'dpi': 300,
            'jpeg_quality': 100,
            'brightness': 0,
            'contrast': 0,
        },
        'c': {
            'name': 'Colored',
            'file_extension': 'jpg',
            'mode': 'RGB',
            'dpi': 200,
            'jpeg_quality': 75,
            'brightness': 0,
            'contrast': 0,
        },
        'g': {
            'name': 'Grayscale',
            'file_extension': 'jpg',
            'mode': 'L',
            'dpi': 200,
            'jpeg_quality': 75,
            'brightness': 0,
            'contrast': 0,
        },
        'pm': {
            'name': 'PDF-Medium Quality',
            'file_extension': 'pdf',
            'mode': 'RGB',
            'dpi': 300,
            'jpeg_quality': 90,
            'brightness': 0,
            'contrast': 0,
        },
        'pc': {
            'name': 'PDF-Colored',
            'file_extension': 'pdf',
            'mode': 'RGB',
            'dpi': 200,
            'jpeg_quality': 75,
            'brightness': 0,
            'contrast': 0,
        },
        'pg': {
            'name': 'PDF-Grayscale',
            'file_extension': 'pdf',
            'mode': 'L',
            'dpi': 200,
            'jpeg_quality': 75,
            'brightness': 0,
            'contrast': 0,
        }
    }
    return profiles


def get_default_profile():
    return get_profiles()['m']


def scan_single_side_main(
        scan_profile=None, print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=False,
        device_uid=None, output_file=None):
    if scan_profile is None:
        scan_profile = get_default_profile()

    device = get_device_quiet_or_choose(
        device_uid=device_uid, print_function=DEFAULT_PRINT_FUNCTION, verbose=False, quiet=quiet)

    pillow_image = scan_side(device=device, scan_profile=scan_profile, return_wia_image=False,
                             print_function=print_function, verbose=verbose, quiet=quiet)

    if not output_file:
        now = datetime.now()
        date_string = now.strftime("%Y-%m-%d_%H-%M-%S")
        file_extension = scan_profile['file_extension']
        output_file = f'scan_{date_string}.{file_extension}'

    save_image_list([pillow_image], filepath=output_file, profile=scan_profile)


def prompt_scan_profile(profiles, print_function=DEFAULT_PRINT_FUNCTION):
    while True:
        default_quality = 'g' if ('g' in profiles) else profiles.keys()[0]
        print('Input quality of document: ')
        for identifier in profiles:
            print(identifier, '-', profiles[identifier]['name'])
        quality = input(
            f'[Default: {default_quality}]: ')
        if len(quality) == 0:
            quality = default_quality
        if quality in profiles:
            return quality

        print_function('Did not understand answer. ')


class MultiImageWriter:
    def __init__(self, filepath, profile):
        self.images = []
        self.filepath = filepath
        self.profile = profile

    def append(self, pillow_image):
        self.images.append(pillow_image)

    def write(self):
        save_image_list(self.images, filepath=self.filepath,
                        profile=self.profile)


def scan_many_documents_flatbed(
        brightness=None, contrast=None, print_function=DEFAULT_PRINT_FUNCTION,
        verbose=False, output_folder=None):
    if not output_folder:
        output_folder = '.'
    else:
        if not os.path.isdir(output_folder):
            raise ValueError(f'Error: {output_folder} is not a directory')

    quiet = False
    device = prompt_choose_device_and_connect(
        print_function=print_function, verbose=verbose, quiet=quiet)

    while True:
        number_of_sides = ask_for_an_int(
            'Input number of sides of this document (0 to stop)', default=1, valid_range=(0, 10000))
        if number_of_sides == 0:
            break

        profiles = get_profiles()
        profile_identifier = prompt_scan_profile(
            print_function=print_function, profiles=profiles)
        profile = profiles[profile_identifier]
        if brightness is not None:
            assert isinstance(brightness, int)
            profile['brightness'] = brightness
        if contrast is not None:
            assert isinstance(contrast, int)
            profile['contrast'] = contrast

        date_string = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"scan_{date_string}.{profile['file_extension']}"
        filepath = os.path.join(output_folder, filename)

        image_writer = MultiImageWriter(filepath=filepath, profile=profile)

        for side in range(number_of_sides):
            if side > 0:
                print_function('Please flip page')
                press_any_key_to_continue()
            print_function(f'Scanning side {side+1} out of {number_of_sides}')
            scan_profile = {key: profile[key] for key in [
                'brightness', 'contrast', 'dpi', 'mode']}
            pillow_image = scan_side(
                device=device, scan_profile=scan_profile, print_function=print_function,
                verbose=verbose, quiet=quiet)
            image_writer.append(pillow_image)

        image_writer.write()
