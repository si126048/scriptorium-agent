!macro NSIS_HOOK_PREINSTALL
  !define /IfNDef HERMENEUT_BACKEND "hermeneut-backend.exe"
  IfFileExists "$INSTDIR\${HERMENEUT_BACKEND}" 0 hermeneut_no_previous
    nsExec::ExecToLog '"$INSTDIR\${HERMENEUT_BACKEND}" local-runtime prepare-upgrade'
    Pop $0
    ${If} $0 != 0
      Abort "研究服务备份或停止失败。研究数据已保留，请关闭程序后重试。"
    ${EndIf}
  hermeneut_no_previous:
!macroend

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "正在为当前用户准备 Hermeneut 本机研究服务…"
  nsExec::ExecToLog '"$INSTDIR\hermeneut-backend.exe" local-runtime install'
  Pop $0
  ${If} $0 != 0
    Abort "本机研究服务尚未安装完成。下载可重试，研究数据保留。"
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::ExecToLog '"$INSTDIR\hermeneut-backend.exe" local-runtime uninstall'
  Pop $0
  ${If} $0 != 0
    Abort "研究后台尚未停止，未删除程序或研究数据。"
  ${EndIf}
!macroend
