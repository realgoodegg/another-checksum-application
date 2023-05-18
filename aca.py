"""
another checksum application (aca)
author: Thomas Luke Ruane
github repo: https://github.com/realgoodegg/another-checksum-application
last modified: 2023-0５-18
"""

import wx
from concurrent import futures
import os
import glob
import hashlib
import shutil
from pubsub import pub

# Thread pool executor for running checksum generation in the background
thread_pool_executor = futures.ThreadPoolExecutor(max_workers=1)


# This class is responsible for generating file hashes
class FileHashingService:
    def __init__(self, get_source_location):
        self.file_data_list = []
        self.get_source_location = get_source_location
        self.hash_verified = None

    # Get the list of files in the source directory
    def get_file_list(self):
        self.file_data_list.clear()
        files_and_hashes = sorted(glob.glob(f"{self.get_source_location}/*.*"))

        # Get the filename and hash string from the .md5 file if one already exists
        for file_path in files_and_hashes:
            file_base = os.path.basename(file_path)
            if os.path.isdir(file_path) or file_path.endswith(".md5"):
                continue
            elif os.path.exists(f"{file_path}.md5"):
                with open(f"{file_path}.md5", "r") as f:
                    file_hash = f.read(32)
            else:
                file_hash = "…"

            file_data = {"filename": file_base, "hash": file_hash}
            self.file_data_list.append(file_data)

    # Generate checksum hash and write to .md5 file
    def generate_hash(self, file_data):
        file_path = os.path.join(self.get_source_location, file_data["filename"])
        file_size = os.path.getsize(
            file_path
        )  # get the file size for updating the update_progress_bar method
        with open(file_path, "rb") as f:
            file_hash = hashlib.md5()
            while chunk := f.read(8192):
                byte_section = (
                    f.tell()
                )  # returns the current position of the file read pointer to update the update_progress_bar method
                file_hash.update(chunk)

                progress_bar_refactor = 0  # adjust update_progress_bar start point according to order of process (generate (0) > copy (33.3) > verify (66.6))

                wx.CallAfter(
                    pub.sendMessage,
                    "update",
                    file_data=file_data,
                    file_size=file_size,
                    byte_section=byte_section,
                    progress_bar_refactor=progress_bar_refactor,
                )  # send to pub.subscribe to update update_progres_bar method

            file_data["hash"] = file_hash.hexdigest()

        with open(f"{file_path}.md5", "w") as f:
            f.write(f"{file_data['hash']}  *{file_data['filename']}")

    # copy file from source > destination
    def copy_file(self, file_data, get_destination_location):
        chunk_size = (
            1024 * 1024
        )  # data chunk size (1MB) to track copy progress and update update_progress_bar method
        source_file = os.path.join(self.get_source_location, file_data["filename"])
        destination_file = os.path.join(get_destination_location, file_data["filename"])
        total_size = os.path.getsize(source_file)
        bytes_copied = 0
        with open(source_file, "rb") as srcf:
            with open(destination_file, "wb") as dstf:
                while True:
                    buffer = srcf.read(chunk_size)
                    if not buffer:
                        break
                    dstf.write(buffer)
                    bytes_copied += len(buffer)
                    progress_bar_refactor = 33.3
                    wx.CallAfter(
                        pub.sendMessage,
                        "update",
                        file_data=file_data,
                        file_size=total_size,
                        byte_section=bytes_copied,
                        progress_bar_refactor=progress_bar_refactor,
                    )
        shutil.copy2(
            f"{source_file}.md5", get_destination_location
        )  # copy .md5 to destination once file copy complete

    # verify existing checksums
    def verify_files(self, file_data, location):
        # pass
        file_path = os.path.join(location, file_data["filename"])
        file_size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            file_hash = hashlib.md5()
            while chunk := f.read(8192):
                byte_section = (
                    f.tell()
                )  # returns the current position of the file read pointer - can be used to update progress bar

                progress_bar_refactor = 66.6
                wx.CallAfter(
                    pub.sendMessage,
                    "update",
                    file_data=file_data,
                    file_size=file_size,
                    byte_section=byte_section,
                    progress_bar_refactor=progress_bar_refactor,
                )
                file_hash.update(chunk)

        hash_string = file_hash.hexdigest()

        with open(f"{file_path}.md5", "r") as hash_file:
            checksum = hash_file.read(32)

        if hash_string == checksum:
            self.hash_verified = True

        elif file_hash != checksum:
            self.hash_verified = False

        else:
            pass


# MainUIFrame Class hosts the UI elements and handles events
class MainUIFrame(wx.Frame):
    def __init__(self):
        self.is_dark_mode = (
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW).GetLuminance() < 1
        )  # detect system dark mode to adjust colour scheme
        self.get_source_loction = None
        self.get_destination_location = None
        self.column_no = None
        self.pass_status = "  ○"
        self.ignore_status = "  -"
        self.fail_status = "  ╳"
        self.selected_items = []  # List of selected items in the source_list
        self.progress_bar_division = 1

        super().__init__(parent=None, title="aca", size=(680, 650))
        self.SetSizeHints(410, 600, -1, -1)

        panel = wx.Panel(self)

        self.set_source_button = wx.Button(panel, label="Select Source Files")
        self.refresh_source_button = wx.Button(panel, label="↻")
        self.source_location = wx.TextCtrl(panel, style=wx.TE_READONLY)

        self.set_destination_button = wx.Button(panel, label="Select Destination ")
        self.destination_location = wx.TextCtrl(panel, style=wx.TE_READONLY)

        self.set_source_button.Bind(wx.EVT_BUTTON, self.set_source_directory)
        self.refresh_source_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.set_destination_button.Bind(wx.EVT_BUTTON, self.set_destination_location)

        self.set_destination_button.Enable(False)
        self.destination_location.Enable(False)
        self.refresh_source_button.Enable(False)

        self.select_button = wx.Button(panel, label="Select All")
        self.clear_button = wx.Button(panel, label="Clear Selected")
        self.select_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.clear_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.select_button.Enable(False)
        self.clear_button.Enable(False)

        self.source_list = wx.ListCtrl(
            panel,
            size=(-1, 660),
            style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES | wx.SUNKEN_BORDER,
        )

        self.source_list.InsertColumn(0, "")
        self.source_list.InsertColumn(1, "")
        self.source_list.InsertColumn(2, "↓", format=wx.LIST_FORMAT_CENTER)
        self.source_list.InsertColumn(3, "→", format=wx.LIST_FORMAT_CENTER)
        self.source_list.InsertColumn(4, "↑", format=wx.LIST_FORMAT_CENTER)
        self.source_list.SetColumnWidth(2, 40)
        self.source_list.SetColumnWidth(3, 40)
        self.source_list.SetColumnWidth(4, 40)

        self.source_list.Bind(wx.EVT_SIZE, self.on_size)
        self.source_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.source_list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_item_deselected)

        self.generate_button = wx.Button(panel, label="Generate ↓")
        self.generate_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.generate_button.Enable(False)

        self.copy_button = wx.Button(panel, label="Copy →")
        self.copy_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.copy_button.Enable(False)

        self.verify_button = wx.Button(panel, label="Verify ↑")
        self.verify_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.verify_button.Enable(False)

        self.progress_bar = wx.Gauge(
            panel,
            range=100,
            size=(200, 50),
            style=wx.GA_HORIZONTAL | wx.GA_SMOOTH | wx.GA_TEXT,
        )

        pub.subscribe(self.update_progress_bar, "update")

        self.status_report = self.CreateStatusBar(2)

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
            self.clear_button, 0, wx.TOP | wx.BOTTOM | wx.EXPAND, 8
        )

        self.destination_layout = wx.BoxSizer(wx.HORIZONTAL)
        self.destination_layout.Add(
            self.set_destination_button, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 3
        )
        self.destination_layout.Add(
            self.destination_location, 1, wx.LEFT | wx.EXPAND, 6
        )

        self.process_buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.process_buttons.Add(self.generate_button, 0, wx.ALL | wx.EXPAND, 4)
        self.process_buttons.Add(self.copy_button, 1, wx.ALL | wx.EXPAND, 4)
        self.process_buttons.Add(self.verify_button, 0, wx.ALL | wx.EXPAND, 4)

        # Main vertical layout for the UI elements
        self.vertical_layout = wx.BoxSizer(wx.VERTICAL)
        self.vertical_layout.Add(self.source_layout, 0, wx.ALL | wx.EXPAND, 6)
        self.vertical_layout.Add(self.destination_layout, 0, wx.ALL | wx.EXPAND, 8)
        self.vertical_layout.Add(
            self.selection_layout, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 60
        )
        self.vertical_layout.Add(self.source_list, 1, wx.ALL | wx.EXPAND, 8)
        self.vertical_layout.Add(
            self.process_buttons, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 60
        )
        self.vertical_layout.Add(
            self.progress_bar, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 100
        )

        panel.SetSizerAndFit(self.vertical_layout)

    # Resize the columns in ListCtrl to fit window resizing
    def on_size(self, event):
        width = (
            self.source_list.GetClientSize().GetWidth() - 120
        )  # -120 to retain thhe status symbol columns (40px * 3)

        columns = (
            self.source_list.GetColumnCount() - 3
        )  # -3 excludes status symbol columns from resize
        column_width = width // columns
        for i in range(columns):
            self.source_list.SetColumnWidth(i, column_width)

        event.Skip()

    def set_source_directory(self, event):
        # clear previous status reports and reset the progress bar
        self.status_report.SetStatusText("", 0)
        self.status_report.SetStatusText("", 1)
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

                # call FileHashingService Class and pass the source directory
                self.fhs = FileHashingService(self.get_source_location)

                # Get the file list from the get_file_lsit method and populate the list view
                self.fhs.get_file_list()
                self.populate_list_view()
                self.set_destination_button.Enable(True)
                self.destination_location.Enable(True)
                self.refresh_source_button.Enable(True)
                self.select_button.Enable(True)
            else:
                self.status_report.SetStatusText("No Directory Set")

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
            self.status_report.SetStatusText(
                f"{total_files} files found, {with_hash} files with checksums"
            )
        else:
            self.status_report.SetStatusText(
                "There are no files in the directory ¯\_(ツ)_/¯"
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
            else:
                self.status_report.SetStatusText("No Copy Location Set")

    def on_item_selected(self, event):
        index = event.GetIndex()
        data = self.source_list.GetItem(index, 1).GetText()

        if index not in self.selected_items:
            self.selected_items.append(index)

            self.clear_button.Enable(True)
            self.generate_button.Enable(True)

        if data != "…":
            self.verify_button.Enable(True)

        if data == "…":
            self.verify_button.Enable(False)

        if self.destination_location.GetValue() != "":
            self.copy_button.Enable(True)

    def on_item_deselected(self, event):
        index = event.GetIndex()
        if index in self.selected_items:
            self.selected_items.remove(index)

        if len(self.selected_items) == 0:
            self.clear_button.Enable(False)
            self.generate_button.Enable(False)
            self.copy_button.Enable(False)

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
        self.status_report.SetStatusText(
            f"Current File: {round(percent)}%  |  {file_data['filename']}", 0
        )

    def update_total_progress(self, current_item, max_value):
        total_progress = int((current_item / max_value) * 100)
        self.status_report.SetStatusText(
            f"Total Progress: {total_progress}%  |  {current_item} of {max_value} Files Complete",
            1,
        )
        if total_progress == 100:
            self.set_source_button.Enable(True)
            self.refresh_source_button.Enable(True)

    def on_generate(self, current_item, max_value, file_index, file_data):
        # Run file hashing service and call list view update and progress bar update when complete
        self.set_source_button.Enable(False)
        self.refresh_source_button.Enable(False)
        self.select_button.Enable(False)
        self.clear_button.Enable(False)
        self.generate_button.Enable(False)

        self.column_no = 2

        if file_data["hash"] == "…":
            self.fhs.generate_hash(file_data)
            wx.CallAfter(self.insert_list_view, file_index, file_data)
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.pass_status
            )
            wx.CallAfter(self.update_total_progress, current_item, max_value)
        else:
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.ignore_status
            )
            wx.CallAfter(self.update_total_progress, current_item, max_value)

        self.set_source_button.Enable(True)
        self.refresh_source_button.Enable(True)

    def on_verify(self, current_item, max_value, file_index, file_data, location):
        self.column_no = 4
        if file_data["hash"] == "…":
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.ignore_status
            )
        else:
            self.fhs.verify_files(file_data, location)
            if self.fhs.hash_verified:
                wx.CallAfter(
                    self.update_status, file_index, self.column_no, self.pass_status
                )

            else:
                wx.CallAfter(
                    self.update_status, file_index, self.column_no, self.fail_status
                )
        wx.CallAfter(self.update_total_progress, current_item, max_value)
        # wx.CallAfter(self.verification_status)

    def on_copy(self, current_item, max_value, file_index, file_data):
        self.set_source_button.Enable(False)
        self.refresh_source_button.Enable(False)
        self.select_button.Enable(False)
        self.clear_button.Enable(False)
        self.generate_button.Enable(False)
        self.progress_bar.SetValue(0)

        # service to generate checksums
        self.column_no = 2
        if file_data["hash"] == "…":
            self.fhs.generate_hash(file_data)
            wx.CallAfter(self.insert_list_view, file_index, file_data)
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.pass_status
            )
        else:
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.ignore_status
            )

        # service to copy files
        self.column_no = 3
        file_destination_check = os.path.join(
            self.get_destination_location, file_data["filename"]
        )
        if not os.path.exists(self.get_destination_location):
            self.status_report.SetStatusText(
                f"{self.get_destination_location} not available, please check the copy location"
            )
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.fail_status
            )

        elif os.path.isfile(file_destination_check):
            self.status_report.SetStatusText(
                f"{file_data['filename']} EXISTS in {self.get_destination_location} SKIPPING copy"
            )
            wx.CallAfter(
                self.update_status, file_index, self.column_no, self.ignore_status
            )

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

            # service to verify file at destination after copy
            self.on_verify(
                current_item,
                max_value,
                file_index,
                file_data,
                self.get_destination_location,
            )
            wx.CallAfter(self.update_total_progress, current_item, max_value)

        self.selected_items.clear()
        self.set_source_button.Enable(True)
        self.refresh_source_button.Enable(True)

    # Handle button presses for simple actions and thread submissions
    def on_button_press(self, event):
        button_label = event.GetEventObject().GetLabel()

        if button_label == "↻":
            self.source_list.DeleteAllItems()
            self.selected_items.clear()
            self.status_report.SetStatusText("")
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
            self.clear_button.Enable(False)
            self.generate_button.Enable(False)

        elif button_label == "Generate ↓":
            self.progress_bar.SetValue(0)
            if len(self.selected_items) > 0:
                max_value = len(
                    self.selected_items
                )  # set the item range for the progress bar
                current_item = 0  # set item number variable to update progress bar, -1 starts the count from 0
                self.status_report.SetStatusText(
                    f"Total Progress: 0%  |  {current_item} of {max_value} Files Complete",
                    1,
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
            self.progress_bar_division = 3
            self.progress_bar.SetValue(0)
            if len(self.selected_items) > 0:
                max_value = len(
                    self.selected_items
                )  # set the item range for the progress bar
                current_item = 0  # set item number variable to update progress bar
                self.status_report.SetStatusText(
                    f"Total Progress: 0%  |  {current_item} of {max_value} Files Complete",
                    1,
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
            if len(self.selected_items) > 0:
                max_value = len(
                    self.selected_items
                )  # set the item range for the progress bar
                current_item = 0  # set item number variable to update progress bar
                self.status_report.SetStatusText(
                    f"Total Progress: 0%  |  {current_item} of {max_value} Files Complete",
                    1,
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


if __name__ == "__main__":
    app = wx.App()
    frame = MainUIFrame()
    frame.Show()
    app.MainLoop()
