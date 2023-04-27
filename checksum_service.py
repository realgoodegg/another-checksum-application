import os
import glob
import hashlib


# This class is responsible for generating file hashes
class FileHashingService:
    def __init__(self, get_source_location):
        self.file_data_list = []
        self.get_source_location = get_source_location
        self.generated_hash = None


    # Get the list of files in the source directory
    def get_file_list(self):
        self.file_data_list.clear()
        files_and_hashes = sorted(glob.glob(f"{self.get_source_location}/*.*"))

        # Get the filename and hash from the .md5 file if it exists
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

    # Generate the hash and write the .md5 file
    def generate_hash(self, file_data):
        file_path = os.path.join(self.get_source_location, file_data["filename"])
        with open(file_path, "rb") as f:
            file_hash = hashlib.md5()
            while chunk := f.read(8192):
                file_hash.update(chunk)
            file_data["hash"] = file_hash.hexdigest()

        with open(f"{file_path}.md5", "w") as f:
            f.write(f"{file_data['hash']}  *{file_data['filename']}")
