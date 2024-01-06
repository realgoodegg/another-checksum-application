"""
another checksum application (aca)
author: Thomas Luke Ruane
github repo: https://github.com/realgoodegg/another-checksum-application
version: 1.1.0
last modified: 2024-01-04

"""
import wx
import logging
import time
from concurrent import futures
import os
from pubsub import pub
import filehashingservice
import subprocess
import pyperclip
from datetime import timedelta


### set up logging
def initialise_logging():
    try:
        if not os.path.isdir("~/Documents/aca"):
            os.mkdir(os.path.expanduser("~/Documents/aca"))
    except OSError:
        pass

    log_file_location = os.path.expanduser("~/Documents/aca/logs")

    if not os.path.isdir(log_file_location):
        os.mkdir(log_file_location)
    else:
        pass

    return log_file_location


log_file_location = initialise_logging()
log_timestamp = time.strftime("%Y%m%d%H%M%S_aca.log")
log_write = os.path.join(log_file_location, log_timestamp)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s:%(module)s:%(levelname)s:%(message)s")
file_handler = logging.FileHandler(log_write)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

### Initiate threading to file processing off the main thread
thread_pool_executor = futures.ThreadPoolExecutor(max_workers=1)


### UI tab panels
class TabPanel(wx.Notebook):
    def __init__(self, parent):
        wx.Notebook.__init__(self, parent)

        aca_panel = AcaInterface(self)
        report_panel = ReportInterface(self)

        self.AddPage(aca_panel, "aca")
        self.AddPage(report_panel, "Report")


### Main UI frame to hold the tab panels
class MainUIFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, title="aca", size=(720, 700))
        self.SetSizeHints(660, 650, -1, -1)

        tab_panels = TabPanel(self)
        main_ui_sizer = wx.BoxSizer(wx.VERTICAL)
        main_ui_sizer.Add(tab_panels, 1, wx.ALL | wx.EXPAND, 10)
        self.SetSizer(main_ui_sizer)

        ### status bar used to show the user messages
        self.live_reporting_status_bar = self.CreateStatusBar(2)

        self.Show()

        ### pubsub message subscription for the live_reporting_status_bar
        pub.subscribe(self.status_message_updater, "status_message_update")

    def status_message_updater(self, message, column):
        self.live_reporting_status_bar.PushStatusText(message, column)


### main application UI
class AcaInterface(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.is_dark_mode = (
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW).GetLuminance() < 1
        )  # detect system dark mode to adjust colour scheme
        self.get_source_location = None
        self.get_destination_location = None
        self.column_no = None
        self.pass_status = "  ○"
        self.ignore_status = "  -"
        self.fail_status = "  X"
        self.selected_items = []  # List of selected items in the ui_file_list
        self.progress_bar_division = 1
        self.start_time = None
        self.end_time = None

        ### initialise Report page status lists
        self.generate_complete = []
        self.generate_skip = []
        self.copy_complete = []
        self.copy_fail = []
        self.copy_skip = []
        self.verify_complete = []
        self.verify_skip = []
        self.verify_fail = []

        super().__init__(parent)

        ### aca interface elements
        self.set_source_button = wx.Button(self, label="Select Source Files")
        self.refresh_state_button = wx.Button(self, label="↻")
        self.source_location = wx.TextCtrl(self, style=wx.TE_READONLY)

        self.set_source_button.Bind(wx.EVT_BUTTON, self.set_source_directory)
        self.refresh_state_button.Bind(wx.EVT_BUTTON, self.on_button_press)

        self.set_destination_button = wx.Button(self, label="Select Destination ")
        self.destination_location = wx.TextCtrl(self, style=wx.TE_READONLY)

        self.set_destination_button.Bind(wx.EVT_BUTTON, self.set_destination_location)

        self.select_all_button = wx.Button(self, label="Select All")
        self.clear_selected_button = wx.Button(self, label="Clear Selected")

        self.select_all_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.clear_selected_button.Bind(wx.EVT_BUTTON, self.on_button_press)

        ### aca interface central file list
        self.ui_file_list = wx.ListCtrl(
            self,
            size=(-1, 660),
            style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES | wx.SUNKEN_BORDER,
        )

        self.ui_file_list.InsertColumn(0, "FILE")
        self.ui_file_list.InsertColumn(1, "CHECKSUM")
        self.ui_file_list.InsertColumn(2, "↓", format=wx.LIST_FORMAT_CENTER)
        self.ui_file_list.InsertColumn(3, "→", format=wx.LIST_FORMAT_CENTER)
        self.ui_file_list.InsertColumn(4, "↑", format=wx.LIST_FORMAT_CENTER)
        self.ui_file_list.SetColumnWidth(2, 40)
        self.ui_file_list.SetColumnWidth(3, 40)
        self.ui_file_list.SetColumnWidth(4, 40)

        # list_font = wx.Font(wx.FontInfo(13).Family(wx.MODERN))
        # self.ui_file_list.SetFont(list_font) # alternative ui_file_list monospaced font

        self.ui_file_list.Bind(wx.EVT_SIZE, self.on_size)
        self.ui_file_list.Bind(
            wx.EVT_LIST_ITEM_SELECTED, self.ui_file_list_item_selected
        )
        self.ui_file_list.Bind(
            wx.EVT_LIST_ITEM_DESELECTED, self.ui_file_list_item_deselected
        )

        ### aca file opration buttons
        self.generate_button = wx.Button(self, label="Generate ↓")
        self.copy_button = wx.Button(self, label="Copy →")
        self.verify_button = wx.Button(self, label="Verify ↑")

        self.generate_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.copy_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.verify_button.Bind(wx.EVT_BUTTON, self.on_button_press)

        ### file processing live progress bar
        self.progress_bar = wx.Gauge(
            self,
            range=100,
            size=(200, 15),
            style=wx.GA_HORIZONTAL | wx.GA_SMOOTH | wx.GA_TEXT,
        )

        ### aca interface layout
        self.source_layout = wx.BoxSizer(wx.HORIZONTAL)
        self.source_layout.Add(
            self.set_source_button, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 4
        )
        self.source_layout.Add(
            self.source_location, 1, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 4
        )
        self.source_layout.Add(
            self.refresh_state_button, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 4
        )

        self.selection_layout = wx.BoxSizer(wx.HORIZONTAL)
        self.selection_layout.Add(
            self.select_all_button, 1, wx.TOP | wx.BOTTOM | wx.RIGHT | wx.EXPAND, 8
        )
        self.selection_layout.Add(
            self.clear_selected_button, 1, wx.TOP | wx.BOTTOM | wx.EXPAND, 8
        )

        self.destination_layout = wx.BoxSizer(wx.HORIZONTAL)
        self.destination_layout.Add(
            self.set_destination_button, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 3
        )
        self.destination_layout.Add(
            self.destination_location, 1, wx.LEFT | wx.EXPAND, 6
        )

        self.source_destination_stack = wx.BoxSizer(wx.VERTICAL)
        self.source_destination_stack.Add(self.source_layout, 0, wx.ALL | wx.EXPAND, 6)
        self.source_destination_stack.Add(
            self.destination_layout, 0, wx.ALL | wx.EXPAND, 8
        )
        self.source_destination_stack.Add(
            self.selection_layout, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 60
        )

        self.process_buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.process_buttons.Add(self.generate_button, 0, wx.ALL | wx.EXPAND, 4)
        self.process_buttons.Add(self.copy_button, 1, wx.ALL | wx.EXPAND, 4)
        self.process_buttons.Add(self.verify_button, 0, wx.ALL | wx.EXPAND, 4)

        self.progress_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.progress_sizer.Add(self.progress_bar, 1, wx.ALL | wx.EXPAND, 15)

        ### aca vertial layout stack
        self.aca_vertical_stack = wx.BoxSizer(wx.VERTICAL)
        self.aca_vertical_stack.Add(
            self.source_destination_stack, 1, wx.LEFT | wx.RIGHT | wx.EXPAND, 30
        )
        self.aca_vertical_stack.Add(self.ui_file_list, 1, wx.ALL | wx.EXPAND, 8)
        self.aca_vertical_stack.Add(
            self.process_buttons, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 60
        )
        self.aca_vertical_stack.Add(
            self.progress_sizer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 100
        )

        self.SetSizerAndFit(self.aca_vertical_stack)

        pub.subscribe(self.update_progress_bar, "progress_update")

        ### set initial button access for aca
        self.initial_button_access()

    ### adjust the ui_file_list to resize in proportion to the interface
    def on_size(self, event):
        width = (
            self.ui_file_list.GetClientSize().GetWidth() - 120
        )  # -120 to retain the status symbol columns (40px * 3)

        columns = (
            self.ui_file_list.GetColumnCount() - 3
        )  # -3 excludes status symbol columns from resize
        column_width = width // columns
        for i in range(columns):
            self.ui_file_list.SetColumnWidth(i, column_width)

        event.Skip()

    ### initial button access at start up
    def initial_button_access(self):
        self.set_source_button.Enable(True)
        self.refresh_state_button.Enable(True)

        self.select_all_button.Enable(False)
        self.clear_selected_button.Enable(False)
        self.generate_button.Enable(False)
        self.copy_button.Enable(False)
        self.verify_button.Enable(False)

        if self.get_destination_location != None:
            self.set_destination_button.Enable(True)

    ### Disable buttons during operations
    def disable_buttons(self):
        self.set_source_button.Enable(False)
        self.set_destination_button.Enable(False)
        self.refresh_state_button.Enable(False)
        self.select_all_button.Enable(False)
        self.clear_selected_button.Enable(False)
        self.generate_button.Enable(False)
        self.copy_button.Enable(False)
        self.verify_button.Enable(False)

    ### enable buttons to start file processing operations
    def enable_buttons(self):
        self.set_source_button.Enable(True)
        self.set_destination_button.Enable(True)
        self.refresh_state_button.Enable(True)
        self.select_all_button.Enable(True)
        self.clear_selected_button.Enable(True)
        self.generate_button.Enable(True)
        self.verify_button.Enable(True)

        if self.get_destination_location != None:
            self.copy_button.Enable(True)

    ### open the source location dialog for the user to select and set
    def set_source_directory(self, event):
        ### clear previous status reports and reset the progress bar
        pub.sendMessage("status_message_update", message="", column=0)
        pub.sendMessage("status_message_update", message="", column=1)
        self.progress_bar.SetValue(0)

        self.source_location.Clear()
        self.ui_file_list.DeleteAllItems()
        with wx.DirDialog(
            self, "Choose a directory:", style=wx.DD_DEFAULT_STYLE
        ) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.get_source_location = dialog.GetPath()
                self.source_location.write(self.get_source_location)

                ### call the filehashingservice and pass the source directory to it
                self.fhs = filehashingservice.FileHashingService(
                    self.get_source_location
                )

                ### publisher to send source location to Report page
                pub.sendMessage(
                    "source_report_update",
                    data=self.get_source_location,
                )
                ### Get the file list from the get_file_list method and populate the list view
                self.fhs.get_file_list()
                self.populate_ui_file_list_view()

            else:
                pub.sendMessage(
                    "status_message_update", message="No Directory Set", column=0
                )
                pass

    ### writes the filename and hash labels to the ui_file_list
    def set_item_labels(self, index, data):
        self.ui_file_list.SetItem(index, column=0, label=str(" " + data["filename"]))
        self.ui_file_list.SetItem(index, column=1, label=str(" " + data["hash"]))

    ### alternates each row colour on the ui_file_list for better visibility
    def ui_list_row_colour(self, file_index):
        if file_index % 2 and self.is_dark_mode:
            self.ui_file_list.SetItemBackgroundColour(
                file_index, (wx.Colour(40, 40, 40))
            )
        elif file_index % 2:
            self.ui_file_list.SetItemBackgroundColour(
                file_index, (wx.Colour(240, 240, 240))
            )
        else:
            pass

    ### populates the ui_file_list view with the filehashingservice.file_data_list
    def populate_ui_file_list_view(self):
        if len(self.fhs.file_data_list) != 0:
            for file_index, file_data in enumerate(self.fhs.file_data_list, start=0):
                self.ui_file_list.InsertItem(file_index, file_data["filename"])
                self.set_item_labels(file_index, file_data)
                self.ui_list_row_colour(file_index)

            ### publisher sends the number of files found and the number of files with checksums to live_reporting_status_bar
            total_files = len(self.fhs.file_data_list)
            no_hash = [data["hash"] for data in self.fhs.file_data_list].count(
                self.fhs.empty_state
            )
            with_hash = int(total_files - no_hash)
            pub.sendMessage(
                "status_message_update",
                message=f"{total_files} files found, {with_hash} files with checksums",
                column=0,
            )

            self.enable_buttons()

        else:
            pub.sendMessage(
                "status_message_update",
                message="There are no files in the directory ¯\_(ツ)_/¯",
                column=0,
            )

    ### open the destination location dialog for the user to select and set
    def set_destination_location(self, event):
        self.destination_location.Clear()

        with wx.DirDialog(
            self, "Choose a directory:", style=wx.DD_DEFAULT_STYLE
        ) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.get_destination_location = dialog.GetPath()
                self.destination_location.write(self.get_destination_location)

                ### publisher sends destination location to the Report page
                pub.sendMessage(
                    "destination_report_update", data=self.get_destination_location
                )

                self.enable_buttons()

            else:
                pub.sendMessage(
                    "status_message_update", message="No Copy Location Set", column=0
                )

    ### add selected item in ui_file_list to selected_items list for processing
    def ui_file_list_item_selected(self, event):
        index = event.GetIndex()
        data = self.ui_file_list.GetItem(index, 1).GetText()

        if index not in self.selected_items:
            self.selected_items.append(index)

    ### remove deselected item in ui_file_list from the selected_items list
    def ui_file_list_item_deselected(self, event):
        index = event.GetIndex()
        if index in self.selected_items:
            self.selected_items.remove(index)

    ### Insert a new item into the ui_file_list view
    def insert_list_view(self, file_index, file_data):
        self.ui_file_list.DeleteItem(file_index)
        self.ui_file_list.InsertItem(file_index, file_data["filename"])
        self.set_item_labels(file_index, file_data)

        self.ui_list_row_colour(file_index)

    ### Update the status column symbols (o, -, x)
    def update_status(self, file_index, column_no, status):
        self.ui_file_list.SetItem(file_index, column=column_no, label=status)

    ### subscribes to filehashingservice publisher to receive file data to update progress_bar
    def update_progress_bar(
        self, file_data, file_size, byte_section, progress_bar_refactor
    ):
        percent = int(((byte_section / file_size) * 100) / self.progress_bar_division)
        if self.progress_bar_division != 1:
            percent += progress_bar_refactor

        self.progress_bar.SetValue(round(percent))

        ### publisher sends file progress updates to the live_reporting_status_bar
        pub.sendMessage(
            "status_message_update",
            message=f"Current File: {round(percent)}%  |  {file_data['filename']}",
            column=0,
        )

    ### reports the total file operations progress to the user
    def update_total_progress(self, current_item, max_value):
        total_progress = int((current_item / max_value) * 100)

        ### publisher sends total progress status messages to live_reporting_status_bar
        pub.sendMessage(
            "status_message_update",
            message=f"Total Progress: {total_progress}%  |  {current_item} of {max_value} Files Complete",
            column=1,
        )
        if not total_progress == 100:
            pass

        else:
            ### 100% file operations complete
            self.end_time = time.time() - self.start_time
            elapsed_time = timedelta(seconds=self.end_time)

            ### publsiher sends elapsed process time to Report page
            pub.sendMessage("time_report_update", data=elapsed_time)

            ### publisher sends file data for generate operations to Report page
            pub.sendMessage("file_report_update", data=self.selected_items)
            pub.sendMessage(
                "generate_report_update",
                data=(self.generate_complete, self.generate_skip),
            )

            ### publisher sends file data for copy operations to Report page
            pub.sendMessage(
                "copy_report_update",
                data=[
                    self.copy_complete,
                    self.copy_skip,
                    self.copy_fail,
                ],
            )

            ### publisher sends file data for verify operations to Report page
            pub.sendMessage(
                "verify_report_update",
                data=[
                    self.verify_complete,
                    self.verify_skip,
                    self.verify_fail,
                ],
            )

            ### clears Report page lists
            self.selected_items.clear()
            self.generate_complete.clear()
            self.generate_skip.clear()
            self.copy_complete.clear()
            self.copy_skip.clear()
            self.copy_fail.clear()
            self.verify_complete.clear()
            self.verify_skip.clear()
            self.verify_fail.clear()

            ### reset intial button access on 100% complete
            self.initial_button_access()

    ### run filehashingservice to generate file checksums
    def on_generate(self, current_item, max_value, file_index, file_data):
        self.column_no = 2

        if file_data["hash"] == self.fhs.empty_state:
            self.fhs.generate_hash(file_data)
            wx.CallAfter(self.insert_list_view, file_index, file_data)
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.pass_status
            )
            wx.CallAfter(self.update_total_progress, current_item, max_value)
            logger.info(f"{file_data['filename']}, {file_data['hash']}, generated")

            self.generate_complete.append(file_data["filename"])
        else:
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.ignore_status
            )
            wx.CallAfter(self.update_total_progress, current_item, max_value)
            logger.info(
                f"{file_data['filename']}, {file_data['hash']}, skipped generate"
            )
            self.generate_skip.append(file_data["filename"])

    ### run filehashingservice to verify checksums
    def on_verify(self, current_item, max_value, file_index, file_data, location):
        self.column_no = 4
        if file_data["hash"] == self.fhs.empty_state:
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.ignore_status
            )
            wx.CallAfter(self.update_total_progress, current_item, max_value)
            logger.info(f"{file_data['filename']}, no hash, skipped verify")
            self.verify_skip.append(file_data["filename"])

        else:
            self.fhs.verify_files(file_data, location)
            if self.fhs.hash_verified:
                wx.CallAfter(
                    self.update_status, file_index, self.column_no, self.pass_status
                )
                wx.CallAfter(self.update_total_progress, current_item, max_value)
                logger.info(f"{file_data['filename']}, {file_data['hash']}, verified")
                self.verify_complete.append(file_data["filename"])
            else:
                wx.CallAfter(
                    self.update_status, file_index, self.column_no, self.fail_status
                )
                logger.critical(
                    f"{file_data['filename']}, {file_data['hash']}, FAILED verification"
                )
                self.verify_fail.append(file_data["filename"])

                wx.CallAfter(self.update_total_progress, current_item, max_value)

    ### run filehashingservice to generate, copy and verify checksums
    def on_copy(self, current_item, max_value, file_index, file_data):
        self.progress_bar.SetValue(0)

        ### service to generate checksums
        self.column_no = 2
        if file_data["hash"] == self.fhs.empty_state:
            self.fhs.generate_hash(file_data)

            wx.CallAfter(self.insert_list_view, file_index, file_data)
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.pass_status
            )
            logger.info(f"{file_data['filename']}, {file_data['hash']}, generated")
            self.generate_complete.append(file_data["filename"])

        else:
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.ignore_status
            )
            logger.info(
                f"{file_data['filename']}, {file_data['hash']}, skipped generate"
            )
            self.generate_skip.append(file_data["filename"])

        ### service to copy files
        self.column_no = 3
        file_destination_check = os.path.join(
            self.get_destination_location, file_data["filename"]
        )

        ### check if destination is still available before copy
        if not os.path.exists(self.get_destination_location):
            pub.sendMessage(
                "status_message_update",
                message=f"{self.get_destination_location} not available",
                column=0,
            )
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.fail_status
            )
            logger.critical(
                f"{self.get_destination_location}, not available, FAILED copy"
            )
            self.copy_fail("copy_report_update", data=file_data["filename"])

        ### check if file exists in destination before copy and skips if true
        elif os.path.isfile(file_destination_check):
            pub.sendMessage(
                "status_message_update",
                message=f"{file_data['filename']} EXISTS",
                column=0,
            )

            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.ignore_status
            )

            logger.warning(
                f"{file_data['filename']}, exists in {self.get_destination_location}, skipped copy"
            )
            self.copy_skip.append(file_data["filename"])

            ### service to verify existing file checksum if present in destination
            if os.path.isfile(f"{file_destination_check}.md5"):
                self.on_verify(
                    current_item,
                    max_value,
                    file_index,
                    file_data,
                    self.get_destination_location,
                )
            else:
                ### skips verification if file in destination has no pre-existing checksum file
                self.column_no = 4
                wx.CallAfter(
                    self.update_status, file_index, self.column_no, self.ignore_status
                )
                logger.warning(
                    f"{file_data['filename']}, has no checksum in {self.get_destination_location}, skipped verify"
                )
                self.verify_skip.append(file_data["filename"])

        else:
            ### service to copy file if not in destination
            self.fhs.copy_file(file_data, self.get_destination_location)
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.pass_status
            )
            logger.info(
                f"{file_data['filename']}, source: {self.get_source_location}, destination: {self.get_destination_location}, successfully copied"
            )
            self.copy_complete.append(file_data["filename"])

            ### service to verify file at destination after copy
            self.on_verify(
                current_item,
                max_value,
                file_index,
                file_data,
                self.get_destination_location,
            )

    def on_button_press(self, event):
        button_label = event.GetEventObject().GetLabel()

        ### User refreshes the source location
        if button_label == "↻":
            self.ui_file_list.DeleteAllItems()
            self.selected_items.clear()
            pub.sendMessage("status_message_update", message="", column=0)
            pub.sendMessage("status_message_update", message="", column=1)
            self.progress_bar.SetValue(0)
            self.fhs.get_file_list()
            self.populate_ui_file_list_view()

        ### user selects all items in ui_file_list
        elif button_label == "Select All":
            for file_index in range(self.ui_file_list.GetItemCount()):
                self.ui_file_list.Select(file_index)

        ### user clears selected items in ui_file_list
        elif button_label == "Clear Selected":
            self.selected_itmes.clear()
            self.ui_file_list.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)

        ### user selects generate file checksums
        elif button_label == "Generate ↓":
            logger.info(f"user selected generate")

            ### disable buttons during file operations
            self.disable_buttons()

            self.start_time = time.time()

            pub.sendMessage("status_message_update", message="", column=1)

            self.progress_bar_division = 1
            self.progress_bar.SetValue(0)

            if len(self.selected_items) > 0:
                max_value = len(
                    self.selected_items
                )  # set the item range for the progress bar
                current_item = 0  # set item number variable to update progress bar, -1 starts the count from 0
                pub.sendMessage(
                    "status_message_update",
                    message=f"Total Progress: 0%  |  {current_item} of {max_value} Files Complete",
                    column=1,
                )
                for index in sorted(self.selected_items):
                    current_item += (
                        1  # increment with each item to update the progress bar
                    )
                    file_data = self.fhs.file_data_list[index]
                    thread_pool_executor.submit(
                        self.on_generate,
                        current_item,
                        max_value,
                        index,
                        file_data,
                    )
            else:
                pass

        ### user selects to generate checksums, copy, verify files
        elif button_label == "Copy →":
            logger.info(f"user selected generate: copy: verify")

            ### disable buttons during file operations
            self.disable_buttons()

            self.start_time = time.time()

            pub.sendMessage("status_message_update", message="", column=1)

            self.progress_bar_division = 3
            self.progress_bar.SetValue(0)

            if len(self.selected_items) > 0:
                max_value = len(
                    self.selected_items
                )  # set the item range for the progress bar
                current_item = 0  # set item number variable to update progress bar
                pub.sendMessage(
                    "status_message_update",
                    message=f"Total Progress: 0%  |  0 of {max_value} Files Complete",
                    column=1,
                )

                for index in sorted(self.selected_items):
                    current_item += (
                        1  # increment with each item to update the progress bar
                    )
                    file_data = self.fhs.file_data_list[index]
                    thread_pool_executor.submit(
                        self.on_copy,
                        current_item,
                        max_value,
                        index,
                        file_data,
                    )

        ### user selects verify file checksums
        elif button_label == "Verify ↑":
            logger.info(f"user selected verify")

            ### disable buttons during file operations
            self.disable_buttons()

            self.start_time = time.time()

            pub.sendMessage("status_message_update", message="", column=1)

            self.progress_bar_division = 1
            self.progress_bar.SetValue(0)

            if len(self.selected_items) > 0:
                max_value = len(
                    self.selected_items
                )  # set the item range for the progress bar
                current_item = 0  # set item number variable to update progress bar
                pub.sendMessage(
                    "status_message_update",
                    message=f"Total Progress: 0%  |  {current_item} of {max_value} Files Complete",
                    column=1,
                )
                for index in sorted(self.selected_items):
                    current_item += (
                        1  # increment with each item to update the progress bar
                    )
                    file_data = self.fhs.file_data_list[index]
                    thread_pool_executor.submit(
                        self.on_verify,
                        current_item,
                        max_value,
                        index,
                        file_data,
                        self.get_source_location,
                    )
        else:
            pass


### Report page UI
class ReportInterface(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        self.is_dark_mode = (
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW).GetLuminance() < 1
        )  # detect system dark mode to adjust colour scheme

        ### Report page UI elements
        self.source_label = wx.StaticText(self, label="Source")
        self.source_stat = wx.TextCtrl(self, value="None", style=wx.TE_READONLY)

        self.destination_label = wx.StaticText(self, label="Destination")
        self.destination_stat = wx.TextCtrl(self, value="None", style=wx.TE_READONLY)

        self.total_files_label = wx.StaticText(self, label="Processed Files")
        self.total_files_stat = wx.TextCtrl(self, value="", style=wx.TE_READONLY)

        self.time_label = wx.StaticText(self, label="Processing Time (h:m:s:ms)")
        self.time_stat = wx.TextCtrl(self, value="00:00:00", style=wx.TE_READONLY)

        self.generate_label = wx.StaticText(self, label="○ Generated")
        self.generate_stat = wx.TextCtrl(self, value="", style=wx.TE_READONLY)

        self.generate_skip_label = wx.StaticText(self, label="- Skipped")
        self.generate_skip_stat = wx.TextCtrl(self, value="", style=wx.TE_READONLY)

        self.generate_space = wx.StaticText(self, label=" ")

        self.copy_label = wx.StaticText(self, label="○ Copied")
        self.copy_stat = wx.TextCtrl(self, value="", style=wx.TE_READONLY)

        self.copy_skip_label = wx.StaticText(self, label="- Skipped ")
        self.copy_skip_stat = wx.TextCtrl(self, value="", style=wx.TE_READONLY)

        self.copy_fail_label = wx.StaticText(self, label="X Failed")
        self.copy_fail_stat = wx.TextCtrl(self, value="", style=wx.TE_READONLY)

        self.verify_label = wx.StaticText(self, label="○ Verified")
        self.verify_stat = wx.TextCtrl(self, value="", style=wx.TE_READONLY)

        self.verify_skip_label = wx.StaticText(self, label="- Skipped")
        self.verify_skip_stat = wx.TextCtrl(self, value="", style=wx.TE_READONLY)

        self.verify_fail_label = wx.StaticText(self, label="X Failed")
        self.verify_fail_stat = wx.TextCtrl(self, value="", style=wx.TE_READONLY)

        stat_font = wx.Font(wx.FontInfo(13).Bold())
        self.total_files_stat.SetFont(stat_font)
        self.time_stat.SetFont(stat_font)
        self.generate_stat.SetFont(stat_font)
        self.generate_skip_stat.SetFont(stat_font)
        self.copy_stat.SetFont(stat_font)
        self.copy_skip_stat.SetFont(stat_font)
        self.copy_fail_stat.SetFont(stat_font)
        self.verify_stat.SetFont(stat_font)
        self.verify_skip_stat.SetFont(stat_font)
        self.verify_fail_stat.SetFont(stat_font)

        source_box = wx.StaticBox(self, -1, "File Locations")
        source_sizer = wx.StaticBoxSizer(source_box, wx.HORIZONTAL)

        source_stack = wx.BoxSizer(wx.VERTICAL)
        source_stack.Add(self.source_label, 0, wx.LEFT | wx.TOP, 5)
        source_stack.Add(self.source_stat, 1, wx.ALL | wx.EXPAND, 5)

        destination_stack = wx.BoxSizer(wx.VERTICAL)
        destination_stack.Add(self.destination_label, 0, wx.LEFT | wx.TOP, 5)
        destination_stack.Add(self.destination_stat, 1, wx.ALL | wx.EXPAND, 5)

        source_sizer.Add(source_stack, 1, wx.EXPAND)
        source_sizer.Add(destination_stack, 1, wx.EXPAND)

        file_box = wx.StaticBox(self, -1, "All Files")
        file_sizer = wx.StaticBoxSizer(file_box, wx.HORIZONTAL)

        file_stack_1 = wx.BoxSizer(wx.VERTICAL)
        file_stack_1.Add(self.total_files_label, 0, wx.LEFT | wx.TOP, 5)
        file_stack_1.Add(self.total_files_stat, 1, wx.ALL | wx.EXPAND, 5)

        file_stack_2 = wx.BoxSizer(wx.VERTICAL)
        file_stack_2.Add(self.time_label, 0, wx.LEFT | wx.TOP, 5)
        file_stack_2.Add(self.time_stat, 1, wx.ALL | wx.EXPAND, 5)

        file_sizer.Add(file_stack_1, 1, wx.EXPAND)
        file_sizer.Add(file_stack_2, 1, wx.EXPAND)

        generate_box = wx.StaticBox(self, -1, "Hash Generation")
        generate_sizer = wx.StaticBoxSizer(generate_box, wx.HORIZONTAL)

        generate_stack_1 = wx.BoxSizer(wx.VERTICAL)
        generate_stack_1.Add(self.generate_label, 0, wx.LEFT | wx.TOP, 5)
        generate_stack_1.Add(self.generate_stat, 1, wx.ALL | wx.EXPAND, 5)

        generate_stack_2 = wx.BoxSizer(wx.VERTICAL)
        generate_stack_2.Add(self.generate_skip_label, 0, wx.LEFT | wx.TOP, 5)
        generate_stack_2.Add(self.generate_skip_stat, 1, wx.ALL | wx.EXPAND, 5)

        generate_stack_3 = wx.BoxSizer(wx.VERTICAL)
        generate_stack_3.Add(self.generate_space, 1, wx.ALL | wx.EXPAND, 5)

        generate_sizer.Add(generate_stack_1, 1, wx.EXPAND)
        generate_sizer.Add(generate_stack_2, 1, wx.EXPAND)
        generate_sizer.Add(generate_stack_3, 1, wx.EXPAND)

        copy_box = wx.StaticBox(self, -1, "File Copy Operations")
        copy_sizer = wx.StaticBoxSizer(copy_box, wx.HORIZONTAL)

        copy_stack_1 = wx.BoxSizer(wx.VERTICAL)
        copy_stack_1.Add(self.copy_label, 0, wx.LEFT | wx.TOP, 5)
        copy_stack_1.Add(self.copy_stat, 1, wx.ALL | wx.EXPAND, 5)

        copy_stack_2 = wx.BoxSizer(wx.VERTICAL)
        copy_stack_2.Add(self.copy_skip_label, 0, wx.LEFT | wx.TOP, 5)
        copy_stack_2.Add(self.copy_skip_stat, 1, wx.ALL | wx.EXPAND, 5)

        copy_stack_3 = wx.BoxSizer(wx.VERTICAL)
        copy_stack_3.Add(self.copy_fail_label, 0, wx.LEFT | wx.TOP, 5)
        copy_stack_3.Add(self.copy_fail_stat, 1, wx.ALL | wx.EXPAND, 5)

        copy_sizer.Add(copy_stack_1, 1, wx.EXPAND)
        copy_sizer.Add(copy_stack_2, 1, wx.EXPAND)
        copy_sizer.Add(copy_stack_3, 1, wx.EXPAND)

        verify_box = wx.StaticBox(self, -1, "Verified Files")
        verify_sizer = wx.StaticBoxSizer(verify_box, wx.HORIZONTAL)

        verify_stack_1 = wx.BoxSizer(wx.VERTICAL)
        verify_stack_1.Add(self.verify_label, 0, wx.LEFT | wx.TOP, 5)
        verify_stack_1.Add(self.verify_stat, 1, wx.ALL | wx.EXPAND, 5)

        verify_stack_2 = wx.BoxSizer(wx.VERTICAL)
        verify_stack_2.Add(self.verify_skip_label, 0, wx.LEFT | wx.TOP, 5)
        verify_stack_2.Add(self.verify_skip_stat, 1, wx.ALL | wx.EXPAND, 5)

        verify_stack_3 = wx.BoxSizer(wx.VERTICAL)
        verify_stack_3.Add(self.verify_fail_label, 0, wx.LEFT | wx.TOP, 5)
        verify_stack_3.Add(self.verify_fail_stat, 1, wx.ALL | wx.EXPAND, 5)

        verify_sizer.Add(verify_stack_1, 1, wx.EXPAND)
        verify_sizer.Add(verify_stack_2, 1, wx.EXPAND)
        verify_sizer.Add(verify_stack_3, 1, wx.EXPAND)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(file_sizer, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
        sizer.Add(generate_sizer, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
        sizer.Add(copy_sizer, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
        sizer.Add(verify_sizer, 0, wx.ALL | wx.EXPAND, 10)

        ### failed files report list
        self.report_list = wx.ListCtrl(
            self,
            size=(-1, 330),
            style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES | wx.SUNKEN_BORDER,
        )

        self.report_list.InsertColumn(0, "FILE")
        self.report_list.InsertColumn(1, "FAILED")
        self.report_list.SetColumnWidth(1, 55)
        self.report_list.Bind(wx.EVT_SIZE, self.on_size)

        ### button to copy filename list to clipboard
        copy_list_button = wx.Button(self, label="Copy to Clipboard")
        copy_list_button.Bind(wx.EVT_BUTTON, self.copy_file_list)

        spacer = wx.StaticText(self, label="")

        ### button to open full log
        log_button = wx.Button(self, label="View Full Log")
        log_button.Bind(wx.EVT_BUTTON, self.view_log)

        h_box = wx.BoxSizer(wx.HORIZONTAL)
        h_box.Add(sizer, 1, wx.EXPAND)
        h_box.Add(self.report_list, 1, wx.ALL | wx.EXPAND, 10)

        button_box = wx.BoxSizer(wx.HORIZONTAL)
        button_box.Add(log_button, 0, wx.ALL, 5)
        button_box.Add(spacer, 1, wx.ALL, 5)
        button_box.Add(copy_list_button, 0, wx.ALL, 5)

        v_box = wx.BoxSizer(wx.VERTICAL)
        v_box.Add(source_sizer, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
        v_box.Add(h_box, 1, wx.EXPAND)
        v_box.Add(button_box, 0, wx.ALL | wx.EXPAND, 5)

        self.SetSizerAndFit(v_box)

        ### subscribers for Report page statistics
        pub.subscribe(self.source_report, "source_report_update")
        pub.subscribe(self.destination_report, "destination_report_update")
        pub.subscribe(self.file_report, "file_report_update")
        pub.subscribe(self.generate_report, "generate_report_update")
        pub.subscribe(self.copy_report, "copy_report_update")
        pub.subscribe(self.verify_report, "verify_report_update")
        pub.subscribe(self.time_report, "time_report_update")

        self.Show()

    def on_size(self, event):
        width = self.report_list.GetClientSize().GetWidth() - 55
        self.report_list.SetColumnWidth(0, width)

        event.Skip()

    def source_report(self, data):
        self.source_stat.Clear()
        self.source_stat.write(data)

    def destination_report(self, data):
        self.destination_stat.Clear()
        self.destination_stat.write(data)

    def file_report(self, data):
        self.total_files_stat.Clear()
        self.total_files_stat.write(str(len(data)))

    def time_report(self, data):
        self.time_stat.Clear()

        self.time_stat.write(str(data)[:-4])

    def generate_report(self, data):
        self.generate_stat.Clear()
        self.generate_skip_stat.Clear()

        self.generate_stat.write(str(len(data[0])))
        self.generate_skip_stat.write(str(len(data[1])))

    def report_list_row_colour(self, file_index):
        if file_index % 2 and self.is_dark_mode:
            self.report_list.SetItemBackgroundColour(
                file_index, (wx.Colour(40, 40, 40))
            )
        elif file_index % 2:
            self.report_list.SetItemBackgroundColour(
                file_index, (wx.Colour(240, 240, 240))
            )

    def copy_report(self, data):
        self.copy_stat.Clear()
        self.copy_skip_stat.Clear()
        self.copy_fail_stat.Clear()
        self.report_list.DeleteAllItems()

        self.copy_stat.write(str(len(data[0])))
        self.copy_skip_stat.write(str(len(data[1])))
        self.copy_fail_stat.write(str(len(data[2])))

        if len(data[2]) > 0:
            for index in range(len(data[2])):
                self.report_list.InsertItem(index, data[2][index])
                self.report_list.SetiItem(index, column=1, label="COPY")
                self.report_list_row_colour(index)

    def verify_report(self, data):
        self.verify_stat.Clear()
        self.verify_skip_stat.Clear()
        self.verify_fail_stat.Clear()
        self.report_list.DeleteAllItems()

        self.verify_stat.write(str(len(data[0])))
        self.verify_skip_stat.write(str(len(data[1])))
        self.verify_fail_stat.write(str(len(data[2])))

        if len(data[2]) > 0:
            for index in range(len(data[2])):
                self.report_list.InsertItem(index, data[2][index])
                self.report_list.SetItem(index, column=1, label="VERIFY")
                self.report_list_row_colour(index)

    def view_log(self, event):
        subprocess.run(["open", log_write])

    def copy_file_list(self, event):
        list_capture = []
        file_list = self.report_list.GetItemCount()
        for index in range(file_list):
            data = self.report_list.GetItem(index, 0).GetText()
            list_capture.append(data)

        pyperclip.copy("\n".join(list_capture))


if __name__ == "__main__":
    app = wx.App()
    frame = MainUIFrame()
    frame.Show()
    app.MainLoop()
