import wx
from checksum_service import FileHashingService
from concurrent import futures
import time

# Thread pool executor for running checksum generation in the background
thread_pool_executor = futures.ThreadPoolExecutor(max_workers=1)


class MainUIFrame(wx.Frame):
    # Main UI Frame Class hosts the UI elements and handles events
    def __init__(self):
        self.is_dark_mode = (
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW).GetLuminance() < 1
        )
        self.get_source_loction = None
        self.green = "○"
        self.orange = "-"
        self.red = "╳"

        super().__init__(parent=None, title="aca", size=(530, 600))
        self.SetSizeHints(410, 600, -1, -1)

        panel = wx.Panel(self)

        self.set_source_button = wx.Button(panel, label="Select Source Files")
        self.refresh_source_button = wx.Button(panel, label="↻")
        self.source_location = wx.TextCtrl(panel, style=wx.TE_READONLY)

        self.set_source_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.refresh_source_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.refresh_source_button.Enable(False)

        self.source_list = wx.ListCtrl(
            panel,
            size=(-1, 520),
            style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES | wx.SUNKEN_BORDER,
        )

        self.source_list.InsertColumn(0, "File")
        self.source_list.InsertColumn(1, "Checksum")
        self.source_list.InsertColumn(2, "", format=wx.LIST_FORMAT_CENTER)
        self.source_list.SetColumnWidth(0, 200)
        self.source_list.SetColumnWidth(1, 200)
        self.source_list.SetColumnWidth(2, 40)

        self.source_list.Bind(wx.EVT_SIZE, self.on_size)

        self.generate_button = wx.Button(panel, label="Generate")
        self.generate_button.Bind(wx.EVT_BUTTON, self.on_button_press)
        self.generate_button.Enable(False)

        self.progress_bar = wx.Gauge(
            panel,
            range=100,
            size=(250, 25),
            style=wx.GA_HORIZONTAL | wx.GA_SMOOTH | wx.GA_TEXT,
        )

        self.status_report = self.CreateStatusBar(1)

        self.source_layout = wx.BoxSizer(wx.HORIZONTAL)
        self.source_layout.Add(
            self.source_location, 2, wx.LEFT | wx.RIGHT | wx.EXPAND, 2
        )
        self.source_layout.Add(
            self.refresh_source_button, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 1
        )

        # Main vertical layout for the UI elements
        self.vertical_layout = wx.BoxSizer(wx.VERTICAL)
        self.vertical_layout.Add(self.set_source_button, 0, wx.ALL | wx.EXPAND, 5)
        self.vertical_layout.Add(self.source_layout, 0, wx.ALL | wx.EXPAND, 5)
        self.vertical_layout.Add(self.source_list, 1, wx.ALL | wx.EXPAND, 5)
        self.vertical_layout.Add(self.generate_button, 0, wx.ALL | wx.EXPAND, 5)
        self.vertical_layout.Add(self.progress_bar, 0, wx.ALL | wx.EXPAND, 8)

        panel.SetSizerAndFit(self.vertical_layout)

    def on_size(self, event):
        # Resize the columns in ListCtrl to fit the window
        width = (
            self.source_list.GetClientSize().GetWidth() - 40
        )  # -40 retain status light column

        columns = (
            self.source_list.GetColumnCount() - 1
        )  # -1 excludes status light column from resize
        column_width = width // columns
        for i in range(columns):
            self.source_list.SetColumnWidth(i, column_width)

        event.Skip()

    def set_source_directory(self):
        # Set the source directory for the file hashing service
        self.source_location.Clear()
        self.source_list.DeleteAllItems()
        with wx.DirDialog(
            self, "Choose a directory:", style=wx.DD_DEFAULT_STYLE
        ) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.get_source_location = dialog.GetPath()
                self.source_location.write(self.get_source_location)

        # call FileHashingService module and pass the source directory
        self.fhs = FileHashingService(self.get_source_location)

        # Get the file list from the file hashing service and populate the list view
        self.fhs.get_file_list()
        self.populate_list_view()
        self.generate_button.Enable(True)
        self.refresh_source_button.Enable(True)

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

    def insert_list_view(self, file_index, file_data):
        # Insert a new item into the list view
        self.source_list.DeleteItem(file_index)
        self.source_list.InsertItem(file_index, file_data["filename"])
        self.set_item_labels(file_index, file_data)
        self.list_colour(file_index)

    def update_status_colour(self, file_index, status):
        # Update the status light column colour
        self.source_list.SetItem(file_index, column=2, label=status)

    def update_progress_bar(self, file_index):
        # Update the progress bar and status bar with the current file being processed
        current_item = int(file_index + 1)
        max_value = len(self.fhs.file_data_list)
        percent = int((current_item / max_value) * 100)
        self.progress_bar.SetValue(percent)
        self.status_report.SetStatusText(
            f"{current_item} of {max_value} files processed"
        )
        if current_item == max_value:
            self.status_report.SetStatusText("All files processed")
            self.set_source_button.Enable(True)
            self.refresh_source_button.Enable(True)

    def on_generate_complete(self, file_index, file_data):
        # Run file hashing service adn call list view update and progress bar update when complete
        self.set_source_button.Enable(False)
        self.refresh_source_button.Enable(False)
        self.generate_button.Enable(False)
        if file_data["hash"] == "…":
            self.fhs.generate_hash(file_data)
            wx.CallAfter(self.insert_list_view, file_index, file_data)
            wx.CallAfter(self.update_status_colour, file_index, self.green)
            wx.CallAfter(self.update_progress_bar, file_index)
        else:
            wx.CallAfter(self.update_progress_bar, file_index)
            wx.CallAfter(self.update_status_colour, file_index, self.orange)
        # time.sleep(
        #     0.1
        # )  # Delay to allow the UI to update before the next file is processed

    def on_button_press(self, event):
        # Handle button presses
        button_label = event.GetEventObject().GetLabel()
        if button_label == "Select Source Files":
            self.status_report.SetStatusText("")
            self.progress_bar.SetValue(0)
            self.set_source_directory()

        elif button_label == "↻":
            self.source_list.DeleteAllItems()
            self.status_report.SetStatusText("")
            self.progress_bar.SetValue(0)
            self.fhs.get_file_list()
            self.populate_list_view()

        elif button_label == "Generate":
            self.status_report.SetStatusText("Generating checksums...")
            for file_index, file_data in enumerate(self.fhs.file_data_list):
                thread_pool_executor.submit(
                    self.on_generate_complete, file_index, file_data
                )  # Run the file hashing service in a thread pool


if __name__ == "__main__":
    app = wx.App()
    frame = MainUIFrame()
    frame.Show()
    app.MainLoop()
