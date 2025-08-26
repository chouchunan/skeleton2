%1%pip3 uninstall FAI_python -y
set FAI_SDK_ROOT_PATH=%CD%\..\..
%1%pip3 install .
::@xcopy /Y /Q build\lib.win-amd64-3.8\FAI_python\*.pyd FAI_python\
for /d %%A in (".\build\lib*") do (
	for %%B in ("%%A\FAI_python\*.pyd") do (
		@xcopy /Y /Q %%B FAI_python\
	)
)
