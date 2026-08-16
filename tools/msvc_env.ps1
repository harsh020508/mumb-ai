$ErrorActionPreference = "Continue"

$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
cmd /c "`"$vcvars`" x64 >nul 2>&1 && set" | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process") }
}

$env:CMAKE_GENERATOR = "Visual Studio 17 2022"
$env:CMAKE_POLICY_VERSION_MINIMUM = "3.5"
$env:PATH = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin;C:\Users\Lucky\orca\simfrancisco\target\sqlite3\bin;$env:PATH"
$env:CMAKE_INCLUDE_PATH = "C:\Users\Lucky\orca\simfrancisco\target\sqlite3\include"
$env:CMAKE_LIBRARY_PATH = "C:\Users\Lucky\orca\simfrancisco\target\sqlite3\lib"
$env:LIBCLANG_PATH = "C:\Users\Lucky\AppData\Local\LLVM18\bin"
$env:RUSTFLAGS = "-l ole32 -l shell32"

