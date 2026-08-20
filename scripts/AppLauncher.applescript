on launchTool()
	set homePath to POSIX path of (path to home folder)
	set launcherPath to homePath & "Library/Application Support/笔记视频提取器/app/scripts/launch.sh"
	do shell script "/bin/zsh " & quoted form of launcherPath & " >/dev/null 2>&1 &"
end launchTool

on run
	launchTool()
end run

on reopen
	launchTool()
end reopen

on idle
	return 30
end idle

on quit
	set homePath to POSIX path of (path to home folder)
	set stopperPath to homePath & "Library/Application Support/笔记视频提取器/app/scripts/stop.sh"
	do shell script "/bin/zsh " & quoted form of stopperPath & " >/dev/null 2>&1" & " || true"
	continue quit
end quit
