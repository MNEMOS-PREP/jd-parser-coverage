@echo off
REM ============================================================
REM  M02 - JD Parser & Coverage Planner, on its own.
REM
REM  This module's services only (PORTS.txt: API 8102).
REM  No sibling repos, so the API answers in its degraded state
REM  and /v1/deps names the module it would have used - which is
REM  the fastest way to check that degradation still works.
REM
REM  Usage:  start_jd.bat          launch M02
REM          start_jd.bat -Check   verify prerequisites only
REM ============================================================

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" -Only m02 -Title "M02 - JD Parser" %*
