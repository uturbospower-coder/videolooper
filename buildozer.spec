[app]

# (str) Title of your application
title = ВидеоЛоопер

# (str) Package name
package.name = videolooper

# (str) Package domain (needed for android/ios packaging)
package.domain = org.example

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas

# (str) Application versioning (method 1)
version = 0.1

# (list) Application requirements
requirements = python3,kivy

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = landscape

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 1

# (list) Permissions
# READ_MEDIA_VIDEO — Android 13+, READ_EXTERNAL_STORAGE — Android 12 и ниже
android.permissions = READ_EXTERNAL_STORAGE,READ_MEDIA_VIDEO,WAKE_LOCK

# (int) Target Android API
android.api = 34

# (int) Minimum API required
android.minapi = 23

# (list) The Android archs to build for
android.archs = arm64-v8a, armeabi-v7a

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
