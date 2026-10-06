' 静默启动「芯选」：让用户双击时看到的就是"界面打开了"，没有控制台黑框。
'
' 为什么不用 --windowed 形态：实测 PyInstaller 的 --windowed 包在受限环境里会
' 静默失败（双击无进程、无日志、无输出），而 --console 形态稳定可用。
' 于是正式包用 --console 内核，由本脚本隐藏窗口；exe 自己再用 --hide-console
' 把控制台藏掉（它才知道自己的 ConsoleWindow 句柄），连黑框一闪都不会有。
'
' 编码要求：VBScript 宿主按 ANSI 读 .vbs。本文件（_utf8）是可编辑源；
' 发布副本 packaging\silent_launch.vbs 由 scripts\make_vbs_gbk.py 生成（GBK）。
Option Explicit

Dim fso, shell, here, app, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
app = here & "\芯选\芯选.exe"

If Not fso.FileExists(app) Then
  MsgBox "XinXuan exe not found:" & vbCrLf & app & vbCrLf & vbCrLf & _
         "Please keep the folder structure intact.", 16, "XinXuan"
  WScript.Quit 1
End If

' 0 = hidden window, False = do not wait for the process to exit。
' --hide-console 让 exe 自己把控制台藏掉，同时也是"静默启动"的信号：
' exe 据此知道没有控制台可用（也就没有 Ctrl+C），退出入口改用原生对话框，
' 并在浏览器交接失败时把地址弹给用户。
' （曾尝试用 WScript.Shell.Environment("Process") 另设一个环境变量，
'   实测会让 shell.Run 返回 0x800700D8，故改用命令行开关这一条路。）
cmd = """" & app & """ --hide-console"
shell.Run cmd, 0, False
WScript.Quit 0
