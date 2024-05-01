import glob
import obspython as obs  # type: ignore
import re
import os
from pathlib import Path

# Rewriting whole script using the Signals!
# "file_changed" signal = lets move the automatically splitted file to a folder
# "get_hooked" procedure = if you start recording and the script didn't get yet notified of the hooking, it will check it itself

# TODO: Implement a way for storing the UUID and Signals that react to it's deletion, etc.
# TODO: Config instead of the Classes storing the data

# Global variables
sourceUUID = None
sett = None

currentRecording = None
gameTitle = "Manual Recording"
isRecording = False


# SIGNAL-RELATED
def start_rec_sh():
    sh = obs.obs_output_get_signal_handler(obs.obs_frontend_get_recording_output())
    obs.signal_handler_connect(sh, "activate", start_rec_cb)


def start_rec_cb(calldata):
    print("------------------------------")
    print("Recording has started...\n")

    global isRecording, currentRecording
    isRecording = True
    currentRecording = None
    print(f"Recording started: {isRecording}")
    print(f"CurrentRecording is {currentRecording}")
    print("------------------------------")


def file_changed_sh():
    sh = obs.obs_output_get_signal_handler(obs.obs_frontend_get_recording_output())
    obs.signal_handler_connect(sh, "file_changed", file_changed_cb)


def file_changed_cb(calldata):
    print("------------------------------")
    print("Refreshing sourceUUID...")
    refresh_source_uuid()

    print("Running get_hooked procedure to get current app title...")
    check_if_hooked_and_update_title()

    print("Recording automatic splitting detected!")
    print("Moving saved recording...")

    # GETTING THE PREVIOUS FILE FIRST
    # I'm not happy with that, but it will have to do
    global currentRecording
    currentRecording = find_latest_file(Settings.OutputDir, Settings.ExtensionMask)
    print(f"Saved recording: {currentRecording}")

    file = File(customPath=currentRecording)
    file.create_new_folder()
    file.remember_and_move()

    print("Done!")
    print(f"New path: {file.get_newPath()}")

    currentRecording = None
    currentRecording = obs.calldata_string(calldata, "next_file")
    print(f"Current file: {currentRecording}")
    print("------------------------------")


def stop_rec_sh():
    output = obs.obs_frontend_get_recording_output()
    sh = obs.obs_output_get_signal_handler(output)
    obs.signal_handler_connect(sh, "stop", stop_rec_cb)
    obs.obs_output_release(output)


def stop_rec_cb(calldata):
    print("------------------------------")
    print("Refreshing sourceUUID...")
    refresh_source_uuid()

    print("Recording has stopped, moving the last file into right folder...")
    print("Running get_hooked procedure to get current app title...")
    check_if_hooked_and_update_title()

    global currentRecording, isRecording
    if currentRecording is None:
        currentRecording = find_latest_file(Settings.OutputDir, Settings.ExtensionMask)

    file = File(customPath=currentRecording)
    file.create_new_folder()
    file.remember_and_move()

    print("Job's done. The file was moved.")
    print(f"File: {file.get_filename()}")
    print(f"New path: {file.get_newPath()}")

    currentRecording = None

    OBS_OUTPUT_CODES = dict(
        [
            (0, "OBS_OUTPUT_SUCCESS"),
            (1, "OBS_OUTPUT_BAD_PATH"),
            (2, "OBS_OUTPUT_CONNECT_FAILED"),
            (3, "OBS_OUTPUT_INVALID_STREAM"),
            (4, "OBS_OUTPUT_ERROR"),
            (5, "OBS_OUTPUT_DISCONNECTED"),
            (6, "OBS_OUTPUT_UNSUPPORTED"),
            (7, "OBS_OUTPUT_NO_SPACE"),
            (8, "OBS_OUTPUT_ENCODE_ERROR"),
        ]
    )

    output_code = OBS_OUTPUT_CODES.get(obs.calldata_int(calldata, "code"))

    print(f"Output signal returned: {output_code}")
    isRecording = False
    print("------------------------------")


def replay_buffer_handler(event):
    if event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED:
        print("------------------------------")
        print("Saving the Replay Buffer...")

        print("Refreshing sourceUUID...")
        refresh_source_uuid()

        print("Running get_hooked procedure to get current app title...")
        check_if_hooked_and_update_title()

        file = File(isReplay=True)

        file.create_new_folder()

        file.remember_and_move()

        print(f"Old path: {file.get_oldPath()}")
        print(f"New path: {file.get_newPath()}")
        print("------------------------------")


def check_if_hooked_and_update_title():
    global sourceUUID, gameTitle
    calldata = get_hooked(sourceUUID)
    print("Checking if source is hooked to any window...")
    if calldata is not None:
        if not gh_isHooked(calldata):
            obs.calldata_destroy(calldata)
            gameTitle = "Manual Recording"
            return
        print("Hooked!")
        gameTitle = gh_title(calldata)
        print(f"Current GameTitle: {gameTitle}")
    obs.calldata_destroy(calldata)


def get_hooked(uuid):
    source = obs.obs_get_source_by_uuid(uuid)
    cd = obs.calldata_create()
    ph = obs.obs_source_get_proc_handler(source)
    obs.proc_handler_call(ph, "get_hooked", cd)
    obs.obs_source_release(source)
    return cd


def gh_isHooked(calldata) -> bool:
    return obs.calldata_bool(calldata, "hooked")


def gh_title(calldata) -> str:
    return remove_unusable_title_characters(obs.calldata_string(calldata, "title"))


# HELPER FUNCTIONS
def remove_unusable_title_characters(title):
    # Remove non-alphanumeric characters (ex. ':')
    title = re.sub(r"[^A-Za-z0-9 ]+", "", title)
    # Remove whitespaces at the end
    title = "".join(title.rstrip())
    # Remove additional whitespaces
    title = " ".join(title.split())

    return title


def get_recording_source_uuid(configured_source):
    global sourceUUID
    current_scene_as_source = obs.obs_frontend_get_current_scene()

    if current_scene_as_source:
        current_scene = obs.obs_scene_from_source(current_scene_as_source)
        scene_item = obs.obs_scene_find_source_recursive(
            current_scene, configured_source
        )
        if scene_item:
            source = obs.obs_sceneitem_get_source(scene_item)

            try:
                source_uuid = obs.obs_source_get_uuid(source)
            except UnboundLocalError:
                return

    obs.obs_source_release(current_scene_as_source)

    return source_uuid


def refresh_source_uuid():
    global sett, sourceUUID
    s_name = obs.obs_data_get_string(sett, "source")
    if len(s_name) > 0:
        sourceUUID = get_recording_source_uuid(s_name)
    else:
        sourceUUID = None


def find_latest_file(folder_path, file_type):
    files = glob.glob(folder_path + file_type)
    max_file = max(files, key=os.path.getctime)
    return os.path.normpath(max_file)


# OBS FUNCTIONS
def script_load(settings):
    # Loading in settings
    global sett
    sett = settings

    # Loading in Signals
    start_rec_sh()  # Respond to starting recording
    file_changed_sh()  # Respond to splitting the recording (ex. automatic recording split)
    stop_rec_sh()  # Respond to stopping the recording

    # Loading in Frontend events to deal with Replay Buffer saving
    obs.obs_frontend_add_event_callback(replay_buffer_handler)


def script_defaults(settings):
    obs.obs_data_set_default_string(settings, "extension", "mkv")


def script_update(settings):
    # Fetching the Settings
    Settings.AddTitleBool = obs.obs_data_get_bool(settings, "title_before_bool")
    Settings.OutputDir = os.path.normpath(
        obs.obs_data_get_string(settings, "outputdir")
    )

    Settings.Extension = obs.obs_data_get_string(settings, "extension")
    Settings.ExtensionMask = "\*" + Settings.Extension
    print("Updated the settings!")


def script_description():
    desc = (
        "<h3>OBS RecORDER </h3>"
        "<hr>"
        "Renames and organizes recordings/replays into subfolders similar to NVIDIA ShadowPlay (<i>NVIDIA GeForce Experience</i>).<br><br>"
        "<small>Created by:</small> <b>padii</b><br><br>"
        "<h4>Settings:</h4>"
    )
    return desc


def button_pressed():
    pass


def UUID_of_sel_src(props, prop, *args, **kwargs):
    p = obs.obs_properties_get(props, "button")
    refresh_source_uuid()
    obs.obs_property_set_description(p, f"UUID: {sourceUUID}")
    return True


def script_properties():
    props = obs.obs_properties_create()

    # Title checkmark
    bool_p = obs.obs_properties_add_bool(
        props, "title_before_bool", "Add name of the game as a recording prefix"
    )
    obs.obs_property_set_long_description(
        bool_p,
        "Check if you want to have name of the application name appended as a prefix to the recording, else uncheck",
    )

    # Source list
    sources_for_recording = obs.obs_properties_add_list(
        props,
        "source",
        "Capturing source name",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING,
    )
    populate_list_property_with_source_names(sources_for_recording)
    obs.obs_property_set_modified_callback(sources_for_recording, UUID_of_sel_src)

    # UUID of the selected source (debugging only)
    b = obs.obs_properties_add_button(
        props, "button", "Show UUID of selected source", button_pressed
    )
    obs.obs_property_set_modified_callback(b, UUID_of_sel_src)

    # Output directory
    obs.obs_properties_add_path(
        props,
        "outputdir",
        "Recordings folder",
        obs.OBS_PATH_DIRECTORY,
        None,
        str(Path.home()),
    )

    # Extension of file
    obs.obs_properties_add_text(
        props, "extension", "Recording extension", obs.OBS_TEXT_DEFAULT
    )

    return props


def populate_list_property_with_source_names(list_property):
    sources = obs.obs_enum_sources()
    obs.obs_property_list_clear(list_property)
    obs.obs_property_list_add_string(list_property, "", "")
    for source in sources:
        name = obs.obs_source_get_name(source)
        obs.obs_property_list_add_string(list_property, name, name)
    obs.source_list_release(sources)


def script_unload():
    # Clear Settings class
    Settings.AddTitleBool = None
    Settings.Extension = None
    Settings.ExtensionMask = None
    Settings.OutputDir = None

    global sourceUUID, sett, currentRecording, gameTitle, isRecording

    # Clear cached settings and important global values
    sourceUUID = None
    sett = None

    currentRecording = None
    gameTitle = None
    isRecording = False


class Settings:
    """Class that holds data from Script settings to use in script"""

    AddTitleBool = None
    Extension = None
    ExtensionMask = None
    OutputDir = None


class File:
    """Class that allows better control over files for the needs of this script"""

    def __init__(self, customPath=None, isReplay=False) -> None:
        """Create a file based on either specified path or path that was configured in Scripts settings

        Args:
            customPath (str): Path to a file that needs to be moved
            isReplay (bool): Set to true if handled recording is from replay buffer
        """
        self.dataExtension = "." + Settings.Extension
        self.replaysFolderName = "Replays"

        # If this object is created during Replay Buffer handling, it will do additional stuff needed
        if isReplay:
            self.isReplay = isReplay
        else:
            self.isReplay = False

        # Allow to specify a custom path where the file is located.
        if customPath is not None:
            self.path = customPath
        else:
            self.path = find_latest_file(Settings.OutputDir, Settings.ExtensionMask)

        # Prepare paths needed for functions
        self.dir = os.path.dirname(self.path)
        self.rawfile = os.path.basename(self.path)

    def get_filename(self) -> str:
        """Returns the file name

        Returns:
            str: name of a file
        """
        return self.rawfile[: -len(self.dataExtension)] + self.dataExtension

    def get_newFolder(self) -> str:
        if self.isReplay:
            global gameTitle
            return os.path.join(self.dir, gameTitle, self.replaysFolderName)
        else:
            return os.path.join(self.dir, gameTitle)

    def get_newFilename(self) -> str:
        if Settings.AddTitleBool:
            global gameTitle
            return gameTitle + " - " + self.get_filename()
        else:
            return self.get_filename()

    def get_oldPath(self) -> str:
        """Returns previous path the file was located in

        Returns:
            str: previous path of file
        """
        return os.path.join(self.dir, self.get_filename())

    def get_newPath(self) -> str:
        """Returns current path where file is located

        Returns:
            str: current path of file
        """
        return os.path.join(self.get_newFolder(), self.get_newFilename())

    def create_new_folder(self) -> None:
        """Creates a new folder based on title of the captured fullscreen application"""
        if not os.path.exists(self.get_newFolder()):
            os.makedirs(self.get_newFolder())

    def remember_and_move(self) -> None:
        """Remembers the previous location of the file and moves it to a new one"""
        oldPath = self.get_oldPath()
        newPath = self.get_newPath()

        os.renames(oldPath, newPath)
