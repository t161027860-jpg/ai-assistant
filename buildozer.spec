[app]
title = AI Assistant
package.name = aiapp
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1

requirements = python3,kivy==2.2.0,speechrecognition,gtts,pygame,requests,urllib3,chardet,idna,certifi

orientation = portrait
fullscreen = 0

android.permissions = RECORD_AUDIO,INTERNET,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_CONNECT,FOREGROUND_SERVICE
android.api = 31
android.minapi = 21
android.ndk = 25b
android.arch = arm64-v8a
android.allow_backup = True

p4a.branch = master
p4a.source_dir = 
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
