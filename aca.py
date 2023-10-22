"""
another checksum application (aca)
author: Thomas Luke Ruane
github repo: https://github.com/realgoodegg/another-checksum-application
version: 1.1.0
last modified: 2023-10-21

"""

import wx
import logging
import time
from concurrent import futures
import os
from pubsub import pub
import filehashingservice
import webbrowser
import subprocess
import pyperclip
from datetime import timedelta

## set up logging
log_file_location = os.path.join(os.getcwd(), "logs")

if not os.path.isdir(log_file_location):
    os.mkdir("logs")

log_timestamp = time.strftime("%Y%m%d%H%M%S_aca.log")
log_write = os.path.join(log_file_location, log_timestamp)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s:%(module)s:%(levelname)s:%(message)s")
file_handler = logging.FileHandler(log_write)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Thread pool executor for running checksum generation in the background
thread_pool_executor = futures.ThreadPoolExecutor(max_workers=1)


class TabPanel(wx.Notebook):
    def __init__(self, parent):
        wx.Notebook.__init__(self, parent)

        aca_panel = AcaInterface(self)
        report_panel = ReportInterface(self)

        self.AddPage(aca_panel, "aca")
        self.AddPage(report_panel, "Report")


class MainUIFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, title="aca", size=(680, 700))
        self.SetSizeHints(660, 650, -1, -1)

        tab_panels = TabPanel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(tab_panels, 1, wx.ALL | wx.EXPAND, 10)

        menubar = wx.MenuBar()
        app_menu = wx.MenuBar.OSXGetAppleMenu(menubar)

        app_menu.Insert(1, wx.ID_ABOUT, "&About aca")

        github_menu = wx.MenuItem(app_menu, wx.ID_ANY, "&Open Github Repo")
        app_menu.Insert(2, github_menu)

        app_menu.Insert(3, wx.ID_SEPARATOR)

        symbol_menu = wx.MenuItem(app_menu, wx.ID_ANY, "&Symbol Key")
        app_menu.Insert(4, symbol_menu)

        app_menu.Insert(5, wx.ID_SEPARATOR)

        self.Bind(wx.EVT_MENU, self.open_about, id=wx.ID_ABOUT)
        self.Bind(wx.EVT_MENU, self.open_github, github_menu)
        self.Bind(wx.EVT_MENU, self.open_key, symbol_menu)

        self.SetMenuBar(menubar)

        self.SetSizer(sizer)

        self.live_reporting = self.CreateStatusBar(2)

        self.Show()

        pub.subscribe(self.status_message, "status_message")

    def open_about(self, event):
        self.preference_window = AboutInterface()
        self.preference_window.Show()

    def open_github(self, event):
        webbrowser.open("https://github.com/realgoodegg/another-checksum-application")

    def open_key(self, event):
        self.symbol_window = KeyInterface()
        self.symbol_window.Show()

    def status_message(self, message, column):
        self.live_reporting.SetStatusText(message, column)


class AcaInterface(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.is_dark_mode = (
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW).GetLuminance() < 1
        )  # detect system dark mode to adjust colour scheme
        self.get_source_loction = None
        self.get_destination_location = None
        self.column_no = None
        self.pass_status = "  ○"
        self.ignore_status = "  -"
        self.fail_status = "  X"
        self.selected_items = []  # List of selected items in the source_list
        self.progress_bar_division = 1
        self.start_time = None
        self.end_time = None

        # Report lists
        self.generate_complete = []
        self.generate_skip = []
        self.copy_complete = []
        self.copy_fail = []
        self.copy_skip = []
        self.verify_complete = []
        self.verify_skip = []
        self.verify_fail = []

        super().__init__(parent)

        self.set_source_button = wx.Button(self, label="Select Source Files")
        self.refresh_source_button = wx.Button(self, label="↻")
        self.source_location = wx.TextCtrl(self, style=wx.TE_READONLY)

        self.set_source_button.Bind(wx.EVT_BUTTON, self.set_source_directory)
        self.refresh_source_button.Bind(wx.EVT_BUTTON, self.on_button_press)

        self.set_destination_button = wx.Button(self, label="Select Destination ")
        self.destination_location = wx.TextCtrl(self, style=wx.TE_READONLY)

        self.set_destination_button.Bind(wx.EVT_BUTTON, self.set_destination_location)

        self.select_button = wx.Button(self, label="Select All")
        self.clear_button = wx.Button(self, label="Clear Selected")

        self.select_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.clear_button.Bind(wx.EVT_BUTTON, self.on_button_press)

        self.source_list = wx.ListCtrl(
            self,
            size=(-1, 660),
            style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES | wx.SUNKEN_BORDER,
        )

        self.source_list.InsertColumn(0, "File List")
        self.source_list.InsertColumn(1, "Hash List")
        self.source_list.InsertColumn(2, "↓", format=wx.LIST_FORMAT_CENTER)
        self.source_list.InsertColumn(3, "→", format=wx.LIST_FORMAT_CENTER)
        self.source_list.InsertColumn(4, "↑", format=wx.LIST_FORMAT_CENTER)
        self.source_list.SetColumnWidth(2, 40)
        self.source_list.SetColumnWidth(3, 40)
        self.source_list.SetColumnWidth(4, 40)

        self.source_list.Bind(wx.EVT_SIZE, self.on_size)
        self.source_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.source_list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_item_deselected)

        self.generate_button = wx.Button(self, label="Generate ↓")
        self.copy_button = wx.Button(self, label="Copy →")
        self.verify_button = wx.Button(self, label="Verify ↑")

        self.generate_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.copy_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.verify_button.Bind(wx.EVT_BUTTON, self.on_button_press)

        self.progress_bar = wx.Gauge(
            self,
            range=100,
            size=(200, 15),
            style=wx.GA_HORIZONTAL | wx.GA_SMOOTH | wx.GA_TEXT,
        )

        self.source_layout = wx.BoxSizer(wx.HORIZONTAL)
        self.source_layout.Add(
            self.set_source_button, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 4
        )
        self.source_layout.Add(
            self.source_location, 1, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 4
        )
        self.source_layout.Add(
            self.refresh_source_button, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 4
        )

        self.selection_layout = wx.BoxSizer(wx.HORIZONTAL)
        self.selection_layout.Add(
            self.select_button, 1, wx.TOP | wx.BOTTOM | wx.RIGHT | wx.EXPAND, 8
        )
        self.selection_layout.Add(
            self.clear_button, 1, wx.TOP | wx.BOTTOM | wx.EXPAND, 8
        )

        self.destination_layout = wx.BoxSizer(wx.HORIZONTAL)
        self.destination_layout.Add(
            self.set_destination_button, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 3
        )
        self.destination_layout.Add(
            self.destination_location, 1, wx.LEFT | wx.EXPAND, 6
        )

        self.top_container = wx.BoxSizer(wx.VERTICAL)
        self.top_container.Add(self.source_layout, 0, wx.ALL | wx.EXPAND, 6)
        self.top_container.Add(self.destination_layout, 0, wx.ALL | wx.EXPAND, 8)
        self.top_container.Add(
            self.selection_layout, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 60
        )

        self.process_buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.process_buttons.Add(self.generate_button, 0, wx.ALL | wx.EXPAND, 4)
        self.process_buttons.Add(self.copy_button, 1, wx.ALL | wx.EXPAND, 4)
        self.process_buttons.Add(self.verify_button, 0, wx.ALL | wx.EXPAND, 4)

        self.progress_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.progress_sizer.Add(self.progress_bar, 1, wx.ALL | wx.EXPAND, 15)

        # Main vertical layout for the UI elements
        self.vertical_layout = wx.BoxSizer(wx.VERTICAL)
        self.vertical_layout.Add(
            self.top_container, 1, wx.LEFT | wx.RIGHT | wx.EXPAND, 30
        )
        self.vertical_layout.Add(self.source_list, 1, wx.ALL | wx.EXPAND, 8)
        self.vertical_layout.Add(
            self.process_buttons, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 60
        )
        self.vertical_layout.Add(
            self.progress_sizer, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 100
        )

        self.SetSizerAndFit(self.vertical_layout)

        pub.subscribe(self.update_progress_bar, "progress_update")

    def on_size(self, event):
        width = (
            self.source_list.GetClientSize().GetWidth() - 120
        )  # -120 to retain the status symbol columns (40px * 3)

        columns = (
            self.source_list.GetColumnCount() - 3
        )  # -3 excludes status symbol columns from resize
        column_width = width // columns
        for i in range(columns):
            self.source_list.SetColumnWidth(i, column_width)

        event.Skip()

    def set_source_directory(self, event):
        # clear previous status reports and reset the progress bar
        pub.sendMessage("status_message", message="", column=0)
        pub.sendMessage("status_message", message="", column=1)
        self.progress_bar.SetValue(0)

        # Set the source directory for the file hashing service
        self.source_location.Clear()
        self.source_list.DeleteAllItems()
        with wx.DirDialog(
            self, "Choose a directory:", style=wx.DD_DEFAULT_STYLE
        ) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.get_source_location = dialog.GetPath()
                self.source_location.write(self.get_source_location)

                # call FileHashingService and pass the source directory
                self.fhs = filehashingservice.FileHashingService(
                    self.get_source_location
                )
                pub.sendMessage(
                    "source_update",
                    data=self.get_source_location,
                )

                # Get the file list from the get_file_list method and populate the list view
                self.fhs.get_file_list()
                self.populate_list_view()

            else:
                pub.sendMessage("status_message", message="No Directory Set", column=0)
                pass

    def set_item_labels(self, index, data):
        # Set the labels for the list view items
        self.source_list.SetItem(index, column=0, label=str(data["filename"]))
        self.source_list.SetItem(index, column=1, label=str(data["hash"]))

    def list_colour(self, file_index):
        if file_index % 2 and self.is_dark_mode:
            self.source_list.SetItemBackgroundColour(
                file_index, (wx.Colour(40, 40, 40))
            )
        elif file_index % 2:
            self.source_list.SetItemBackgroundColour(
                file_index, (wx.Colour(240, 240, 240))
            )
        else:
            pass

    def populate_list_view(self):
        # Populate the list view with the file list from the file hashing service
        if len(self.fhs.file_data_list) != 0:
            for file_index, file_data in enumerate(self.fhs.file_data_list, start=0):
                self.source_list.InsertItem(file_index, file_data["filename"])
                self.set_item_labels(file_index, file_data)
                self.list_colour(file_index)

            # Update the status bar with the number of files found and the number of files with checksums
            total_files = len(self.fhs.file_data_list)
            no_hash = [data["hash"] for data in self.fhs.file_data_list].count("…")
            with_hash = int(total_files - no_hash)
            pub.sendMessage(
                "status_message",
                message=f"{total_files} files found, {with_hash} files with checksums",
                column=0,
            )
        else:
            pub.sendMessage(
                "status_message",
                message="There are no files in the directory ¯\_(ツ)_/¯",
                column=0,
            )

    def set_destination_location(self, event):
        # Set the destination directory for the file copy location
        self.destination_location.Clear()
        with wx.DirDialog(
            self, "Choose a directory:", style=wx.DD_DEFAULT_STYLE
        ) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.get_destination_location = dialog.GetPath()
                self.destination_location.write(self.get_destination_location)
                pub.sendMessage(
                    "destination_update", data=self.get_destination_location
                )
            else:
                pub.sendMessage(
                    "status_update", message="No Copy Location Set", column=0
                )

    def on_item_selected(self, event):
        index = event.GetIndex()
        data = self.source_list.GetItem(index, 1).GetText()

        if index not in self.selected_items:
            self.selected_items.append(index)

    def on_item_deselected(self, event):
        index = event.GetIndex()
        if index in self.selected_items:
            self.selected_items.remove(index)

    def insert_list_view(self, file_index, file_data):
        # Insert a new item into the list view
        self.source_list.DeleteItem(file_index)
        self.source_list.InsertItem(file_index, file_data["filename"])
        self.set_item_labels(file_index, file_data)

        self.list_colour(file_index)

    def update_status(self, file_index, column_no, status):
        # Update the status column symbol
        self.source_list.SetItem(file_index, column=column_no, label=status)

    def update_progress_bar(
        self, file_data, file_size, byte_section, progress_bar_refactor
    ):
        percent = int(((byte_section / file_size) * 100) / self.progress_bar_division)
        if self.progress_bar_division != 1:
            percent += progress_bar_refactor

        self.progress_bar.SetValue(round(percent))
        pub.sendMessage(
            "status_update",
            message=f"Current File: {round(percent)}%  |  {file_data['filename']}",
            column=0,
        )

    def update_total_progress(self, current_item, max_value):
        total_progress = int((current_item / max_value) * 100)
        pub.sendMessage(
            "status_message",
            message=f"Total Progress: {total_progress}%  |  {current_item} of {max_value} Files Complete",
            column=1,
        )
        if not total_progress == 100:
            pass
        else:
            self.end_time = time.time() - self.start_time
            elapsed_time = timedelta(seconds=self.end_time)

            pub.sendMessage("time_update", data=elapsed_time)

            pub.sendMessage("file_update", data=self.selected_items)
            pub.sendMessage(
                "generate_update",
                data=(self.generate_complete, self.generate_skip),
            )
            pub.sendMessage(
                "copy_update",
                data=[
                    self.copy_complete,
                    self.copy_skip,
                    self.copy_fail,
                ],
            )
            pub.sendMessage(
                "verify_update",
                data=[
                    self.verify_complete,
                    self.verify_skip,
                    self.verify_fail,
                ],
            )

            self.selected_items.clear()
            self.generate_complete.clear()
            self.generate_skip.clear()
            self.copy_complete.clear()
            self.copy_skip.clear()
            self.copy_fail.clear()
            self.verify_complete.clear()
            self.verify_skip.clear()
            self.verify_fail.clear()

    def on_generate(self, current_item, max_value, file_index, file_data):
        # Run file hashing service and call list view update and progress bar update when complete

        self.column_no = 2

        if file_data["hash"] == "…":
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

    def on_verify(self, current_item, max_value, file_index, file_data, location):
        self.column_no = 4
        if file_data["hash"] == "…":
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

    def on_copy(self, current_item, max_value, file_index, file_data):
        self.progress_bar.SetValue(0)

        # service to generate checksums
        self.column_no = 2
        if file_data["hash"] == "…":
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

        # service to copy files
        self.column_no = 3
        file_destination_check = os.path.join(
            self.get_destination_location, file_data["filename"]
        )
        if not os.path.exists(self.get_destination_location):
            pub.sendMessage(
                "status_update",
                message=f"{self.get_destination_location} not available",
                column=0,
            )
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.fail_status
            )
            logger.critical(
                f"{self.get_destination_location}, not available, FAILED copy"
            )
            self.copy_fail("copy_update", data=file_data["filename"])

        elif os.path.isfile(file_destination_check):
            pub.sendMessage(
                "status_update", message=f"{file_data['filename']} EXISTS", column=0
            )
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.ignore_status
            )
            logger.warning(
                f"{file_data['filename']}, exists in {self.get_destination_location}, skipped copy"
            )
            self.copy_skip("copy_update", data=file_data["filename"])

            # service to verify file at destination
            self.on_verify(
                current_item,
                max_value,
                file_index,
                file_data,
                self.get_destination_location,
            )
        else:
            self.fhs.copy_file(file_data, self.get_destination_location)
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.pass_status
            )
            logger.info(
                f"{file_data['filename']}, source: {self.get_source_location}, destination: {self.get_destination_location}, successfully copied"
            )
            self.copy_complete.append(file_data["filename"])

            # service to verify file at destination after copy
            self.on_verify(
                current_item,
                max_value,
                file_index,
                file_data,
                self.get_destination_location,
            )

    def on_button_press(self, event):
        button_label = event.GetEventObject().GetLabel()

        if button_label == "↻":
            self.source_list.DeleteAllItems()
            self.selected_items.clear()
            pub.sendMessage("status_message", message="", column=0)
            pub.sendMessage("status_message", message="", column=1)
            self.progress_bar.SetValue(0)
            self.fhs.get_file_list()
            self.populate_list_view()
            self.select_button.Enable(True)

        elif button_label == "Select All":
            for file_index in range(self.source_list.GetItemCount()):
                self.source_list.Select(file_index)

        elif button_label == "Clear Selected":
            self.selected_items.clear()
            self.source_list.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)

        elif button_label == "Generate ↓":
            logger.info(f"user selected generate")

            self.start_time = time.time()

            pub.sendMessage("status_message", message="", column=1)
            self.progress_bar_division = 1
            self.progress_bar.SetValue(0)
            if len(self.selected_items) > 0:
                max_value = len(
                    self.selected_items
                )  # set the item range for the progress bar
                current_item = 0  # set item number variable to update progress bar, -1 starts the count from 0
                pub.sendMessage(
                    "status_message",
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

        elif button_label == "Copy →":
            logger.info(f"user selected generate: copy: verify")

            self.start_time = time.time()

            pub.sendMessage("status_message", message="", column=1)
            self.progress_bar_division = 3
            self.progress_bar.SetValue(0)
            if len(self.selected_items) > 0:
                max_value = len(
                    self.selected_items
                )  # set the item range for the progress bar
                current_item = 0  # set item number variable to update progress bar
                pub.sendMessage(
                    "status_update",
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
        elif button_label == "Verify ↑":
            logger.info(f"user selected verify")

            self.start_time = time.time()

            pub.sendMessage("status_message", message="", column=1)
            self.progress_bar_division = 1
            self.progress_bar.SetValue(0)

            if len(self.selected_items) > 0:
                max_value = len(
                    self.selected_items
                )  # set the item range for the progress bar
                current_item = 0  # set item number variable to update progress bar
                pub.sendMessage(
                    "status_update",
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


class AboutInterface(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, size=(300, 200))
        self.SetMaxSize(wx.Size(300, 200))
        self.SetMinSize(wx.Size(300, 200))

        panel = wx.Panel(self)

        title = wx.StaticText(panel, -1, "aca (another checksum application)")
        version = wx.StaticText(panel, -1, "Version 1.1.0")
        date = wx.StaticText(panel, -1, "21 October 2023")
        python_v = wx.StaticText(panel, -1, "Python: 3.9.14")
        wxpython_v = wx.StaticText(panel, -1, "wxPython: 4.2.0")

        header_font = wx.Font(wx.FontInfo(13).Bold())
        body_font = wx.Font(wx.FontInfo(11))
        title.SetFont(header_font)
        version.SetFont(body_font)
        date.SetFont(body_font)
        python_v.SetFont(body_font)
        wxpython_v.SetFont(body_font)

        box = wx.StaticBox(panel, -1, "")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        aca_details = wx.BoxSizer(wx.VERTICAL)
        aca_details.Add(title, 0, wx.ALL | wx.ALIGN_CENTRE, 3)
        aca_details.Add(version, 0, wx.ALL | wx.ALIGN_CENTRE, 3)
        aca_details.Add(date, 0, wx.ALL | wx.ALIGN_CENTRE, 3)

        code_details = wx.BoxSizer(wx.VERTICAL)
        code_details.Add(python_v, 0, wx.ALL | wx.ALIGN_CENTRE, 3)
        code_details.Add(wxpython_v, 0, wx.ALL | wx.ALIGN_CENTRE, 3)

        sizer.Add(aca_details, 1, wx.ALL | wx.ALIGN_CENTRE, 10)
        sizer.Add(code_details, 1, wx.ALL | wx.ALIGN_CENTRE, 10)

        panel.SetSizerAndFit(sizer)


class KeyInterface(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, size=(300, 200))
        self.SetMaxSize(wx.Size(300, 200))
        self.SetMinSize(wx.Size(300, 200))

        panel = wx.Panel(self)

        title = wx.StaticText(panel, -1, "aca Symbol Key")
        generate_key = wx.StaticText(panel, -1, "↓  =  Generate Hash")
        copy_key = wx.StaticText(panel, -1, "→  =  Copy File")
        verify_key = wx.StaticText(panel, -1, "↑  =  Verify Hash")

        pass_key = wx.StaticText(panel, -1, "○  =  Pass")
        skip_key = wx.StaticText(panel, -1, "-  =  Skipped")
        fail_key = wx.StaticText(panel, -1, "X  =  Fail")

        header_font = wx.Font(wx.FontInfo(13).Bold())
        title.SetFont(header_font)

        symbol_details = wx.BoxSizer(wx.VERTICAL)
        symbol_details.Add(title, 0, wx.ALL | wx.ALIGN_CENTRE, 15)
        symbol_details.Add(generate_key, 0, wx.LEFT | wx.ALIGN_LEFT, 80)
        symbol_details.Add(copy_key, 0, wx.LEFT | wx.ALIGN_LEFT, 80)
        symbol_details.Add(verify_key, 0, wx.LEFT | wx.ALIGN_LEFT, 80)

        symbol_details.Add(pass_key, 0, wx.LEFT | wx.ALIGN_LEFT, 80)
        symbol_details.Add(skip_key, 0, wx.LEFT | wx.ALIGN_LEFT, 80)
        symbol_details.Add(fail_key, 0, wx.LEFT | wx.ALIGN_LEFT, 80)

        panel.SetSizerAndFit(symbol_details)


class ReportInterface(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

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

        self.report_list = wx.ListCtrl(
            self,
            size=(-1, 330),
            style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES | wx.SUNKEN_BORDER,
        )

        self.report_list.InsertColumn(0, "Failed Files")
        self.report_list.Bind(wx.EVT_SIZE, self.on_size)

        copy_list_button = wx.Button(self, label="Copy to Clipboard")
        copy_list_button.Bind(wx.EVT_BUTTON, self.copy_file_list)

        spacer = wx.StaticText(self, label="")

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

        pub.subscribe(self.source_report, "source_update")
        pub.subscribe(self.destination_report, "destination_update")
        pub.subscribe(self.file_report, "file_update")
        pub.subscribe(self.generate_report, "generate_update")
        pub.subscribe(self.copy_report, "copy_update")
        pub.subscribe(self.verify_report, "verify_update")
        pub.subscribe(self.time_report, "time_update")

        self.Show()

    def on_size(self, event):
        width = self.report_list.GetClientSize().GetWidth()
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
