#!/bin/bash

CONVERT_PATH='./convert'

RED='\033[0;91m'
GREY_B='\033[1;90m'
REV_WHITE="\u001b[47;1;41m"

WB='\033[1;97m'
RES='\033[0m'
function display_help()
{
	printf "$WBusage:\t./tester.sh\n$RES"
	exit
}

if [ "$#" -ne "0" ]
then
	display_help
fi

## check if ./convert is here
convert_ok=$(ls $CONVERT_PATH 2>/dev/null | wc -l)
if [ "$convert_ok" -eq "0" ]
then
	printf "$REDconverter needed, please make it\n$RES"
	exit
fi

## test
function test()
{
	printf "\n$WB$CONVERT_PATH $1$GREY_B\n"
	$CONVERT_PATH $1
}
## Should work

test "'a'"
test "'A'"
test "'\'"
test "'*'"
echo
test "0"
test "0.0"
test "-4.2"
test "4.2"
echo
test "0.0f"
test ".0f"
test "0.f"
test "0."
echo
test "nan"
test "inf"
test "+inff"
test "-inf"
echo
test "42.00001f"
test "42.12"
test "-42.5"
test "42000000000000000000000000000000000000.17"
test "420000000000000000000000000000000000000.17"
test "420000000000000000000000000000000000000.17f"
test "2147483648"
test "2147483648.1"
test "-2147483649"
test "-2147483648"
echo

echo -e "${WB}Invalid Examples:${RES}"
test ".f"
test "-.f"
test "7.77.7"
test "-7.12f1"
test
