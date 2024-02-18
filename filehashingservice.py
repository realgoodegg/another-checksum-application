import wx
import os
import hashlib
import shutil
import glob
from pubsub import pub


# This class is responsible for generating file hashes
class FileHashingService:
    def __init__(self, get_source_location):
        self.file_data_list = []
        self.get_source_location = get_source_location
        self.hash_verified = None
        self.checksum_algorithm = "md5"
        self.empty_state = "\u002F" # empty checksum state "/"

    # Get the list of files in the source directory
    def get_file_list(self):
        self.file_data_list.clear()
        complete_file_list = sorted(glob.glob(f"{self.get_source_location}/*.*"))
        filtered_list = [f for f in complete_file_list if not f.startswith('.') and not f.lower().endswith('.ini') and not (os.name == 'nt' and f.startswith('$'))] # filter out common system and hidden files across os platforms
        files_and_hashes = sorted(filtered_list, key=lambda x: os.path.basename(x).lower())

        # Get the filename and hash string from the .md5 file if one already exists
        for file_path in files_and_hashes:
            file_base = os.path.basename(file_path)
            file_mod_date = os.path.getmtime(file_path)
            if os.path.isdir(file_path) or file_path.endswith(".md5"):
                continue
            elif os.path.exists(f"{file_path}.md5"):
                with open(f"{file_path}.md5", "r") as f:
                    file_hash = f.read(32)
            else:
                file_hash = self.empty_state

            file_data = {"filename": file_base, "hash": file_hash, "mod_date": file_mod_date}
            self.file_data_list.append(file_data)

    # Generate checksum hash and write to .md5 file
    def generate_hash(self, file_data):
        file_path = os.path.join(self.get_source_location, file_data["filename"])
        file_size = os.path.getsize(
            file_path
        )  # get the file size for updating the update_progress_bar method

        file_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                byte_section = (
                    f.tell()
                )  # returns the current position of the file read pointer to update the update_progress_bar method
                file_hash.update(chunk)
                progress_bar_refactor = 0  # adjust update_progress_bar start point according to order of process (generate (0) > copy (33.3) > verify (66.6))

                wx.CallAfter(
                    pub.sendMessage,
                    "progress_update",
                    file_data=file_data,
                    file_size=file_size,
                    byte_section=byte_section,
                    progress_bar_refactor=progress_bar_refactor,
                )  # send to pub.subscribe to update update_progres_bar method

            file_data["hash"] = file_hash.hexdigest()

        with open(f"{file_path}.{self.checksum_algorithm}", "w") as f:
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
                        "progress_update",
                        file_data=file_data,
                        file_size=total_size,
                        byte_section=bytes_copied,
                        progress_bar_refactor=progress_bar_refactor,
                    )

        shutil.copy2(
            f"{source_file}.{self.checksum_algorithm}", get_destination_location
        )  # copy .md5 to destination once file copy complete

    # verify existing checksums
    def verify_files(self, file_data, location):
        file_path = os.path.join(location, file_data["filename"])
        file_size = os.path.getsize(file_path)

        if os.path.exists(f"{file_path}.md5"):
            with open(f"{file_path}.md5", "r") as hash_file:
                checksum = hash_file.read(32)
            file_hash = hashlib.md5()
        else:
            pass

        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                byte_section = (
                    f.tell()
                )  # returns the current position of the file read pointer - can be used to update progress bar

                progress_bar_refactor = 66.6
                wx.CallAfter(
                    pub.sendMessage,
                    "progress_update",
                    file_data=file_data,
                    file_size=file_size,
                    byte_section=byte_section,
                    progress_bar_refactor=progress_bar_refactor,
                )
                file_hash.update(chunk)

        hash_string = file_hash.hexdigest()

        if hash_string == checksum:
            self.hash_verified = True

        elif file_hash != checksum:
            self.hash_verified = False

        else:
            pass
