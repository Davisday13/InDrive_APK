[app]
title = InDrive Finanzas
package.name = indrive_finanzas
package.domain = org.indrive
source.dir = .
source.include_exts = py,png,jpg,db
version = 1.0.0

# Icono y pantalla de inicio (Splash)
icon.filename = icon.png
presplash.filename = presplash.png

# Requerimientos básicos
requirements = python3,kivy

# Orientación vertical para celulares
orientation = portrait
fullscreen = 0

# Permisos
android.permissions = INTERNET

# Configuración de compilación Android
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
