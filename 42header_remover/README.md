# 42 HEADER REMOVER
Checks if a file starts with `TARGET_START_STRING1` or `TARGET_START_STRING2`. If so,
script removes the header (lines 1-11 + following empty new line with only white space) based on `LINES_TO_REMOVE`.

## ARGS
Give a target directory as an argument. Should handle directory with sub directories and sub directories of sub directories inside of them.

## PERMISSIONS
`chmod +x 42header_remover`

## USE
`python3 42header_remover.py <target_directory>` 

## RETURNS
* bool: True if the file was modified, otherwise false.

