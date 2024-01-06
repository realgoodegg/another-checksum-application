# aca

![aca icon](/readme_images/128_icon.png)

**aca** is Another Checksum Application

aca is a **simple GUI application** designed for the purpose of generating MD5 checksums, copying files, and verifying their integrity within a unified process.  aca can generate and verify MD5 checksums as individual processes or by simply hitting the "Copy" button, generate, copy and verify files all in one go!

The aim of the project is to provide **a "one-click" solution for users to securely back-up their digital files** with minimal friction or technical know-how.

![aca demo gif](/readme_images/aca_demo.gif)

_Note, I started this project to learn Python and I know there are many areas the code can be improved - if do take a look at the code, please be nice!_

## Requirements

aca is written in [Python 3.9.x](https://www.python.org) and the UI created in [wxPython 4.2.0](https://wxpython.org/index.html), it was initally built and tested for macOS Somona 14.2.

It requires the following additional Python libraries:

* [pypubsub](https://github.com/schollii/pypubsub)
* [pyperclip](https://github.com/asweigart/pyperclip)

A executable app is available to download in the Release section, otherwise the app can be compiled with [Pyinstaller](https://pyinstaller.org/en/stable/):

`pyinstaller --onefile --windowed --collect-submodules filehashingservice.py --icon aca_icon.icns --name "aca" aca.py`

## Checksum Generation

Checksums files are generated on per file basis and written to a .md5 file containing the 32-bit hexadecimal hash string and the filename:

`122b179147f3a72134877283a9aa8f5d  *filename.mp4`

| ![checksum file](/readme_images/checksum_file.png) |
| :-- |
| _.md5 checksum file_ |

## aca Operation

### Select Files
Click the "Select Source Files" button to open the directory of files you want to process.  

The directory path will be listed in the source dialog.

<!-- ![select source files](/readme_images/1_select_source.jpg) -->

The source files will be listed in the "FILE" column of the main table and any with exisiting .md5 files associated with them will be listed alongside, in the "CHECKSUM" column.  If no checksum file is present the cell will show "/".

| ![file with no checksum](/readme_images/2_empty_state.jpg) |
| :-- |
| _Files without checksums_ |

If the file status in the source location changes for any reason (files added, removed etc.) click the "↻" button to refresh the source files in the file list.

<!-- ![refresh source location](/readme_images/3_refresh.jpg) -->

### Generate, Copy and Verify
Manually select individual files in the list or click the "Select All" to select the entire range.  Click "Clear Selected" button to clear any selected files.

<!-- ![select all and clear all files](/readme_images/4_select_clear_files.jpg) -->

From here you have the option to generate new file checksums by clicking the "Generate ↓" button and where associated .md5 files already exist, verify the existing checksums by clicking the "Verify ↑" button.

If you intend to back-up the files to a new location, click the "Select Destination" button and select a directory.  The directory path will be listed in the destination dialog.

<!-- ![select copy destination](/readme_images/6_select_destination.jpg) -->

Clicking the "Copy →" button, will generate the checksums, copy the files from their source directory to the destination directory and verify the file checksums at the destination.

<!-- ![generate, copy and verify buttons](/readme_images/5_generate_copy_verify.jpg) -->

The central file list, will apply any newly generated checksum hashes to the "CHECKSUM" column.

| ![generated checksum](/readme_images/7_checksum_generated.jpg) |
| :-- |
| _Generated checksums_ |

### Pass, Fail or Skip
Each row in the file list also has a status indicator for each file process:

| Generate | Copy | Verify |
| :--: | :--: | :--: |
| ↓ | → | ↑ |

<!-- ![process symbols](/readme_images/8_symbols.jpg) -->

For each process there is a Pass, Fail and Skip status:

| Pass | Fail | Skip |
| :--: | :--: | :--: |
| ○ | X | \- |

| ![pass state](/readme_images/8_symbols.jpg) |
| :-- |
| Pass status for generate, copy, verify |

| ![ignore and fail state](/readme_images/9_ignore_fail.jpg) |
| :-- |
| Skip and Fail status |


Currently aca does not regenerate existing checksums or overwrite duplicate files in a destination directory when copying, in these circumstances the file operation will be skipped and the user notified in the relevant status column, Report page stat and log.

### Report page and Logging
On completion the Report page to will display an overview of the file operations, including the number of files passed, failed or skipped, for each process, and list any failed files in the right hand table.

| ![report page](/readme_images/10_report_page.jpg) |
| :-- |
| Report page |

The failed file list can be copied to the clipbaord by clicking the "Copy to Clipboard" button and the full log accessed for more details by clicking the "View Full Log" button.

Log files are stored in ~/user/Documents/aca/logs. A log file will be written each time the application is opened.

## CC 4.0 Licence and Usual Disclaimers

[another checksum application \(aca\)](https://github.com/realgoodegg/another-checksum-application)© 2023 by [Thomas Luke Ruane](https://github.com/realgoodegg) is licensed under [CC BY 4.0](http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1)![](cc-logo.f0ab4ebe.svg)[](http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1)![](cc-by.21b728bb.svg)[](http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1)

This software is provided "as is", without warrany or liability. The author takes no responsbility for any system meltdowns or other misfortune that might occur from using this software (though I'm sure it'll be fine).











