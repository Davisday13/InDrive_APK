[app]
title = InDrive Finanzas
package.name = indrive_finanzas
package.domain = org.indrive
source.dir = .
source.include_exts = py,png,jpg,jpeg
version = 1.1.6

icon.filename = icon.png
presplash.filename = presplash.png

# La app solo usa la libreria estandar (urllib) para hablar con Supabase:
# python-for-android NO tiene receta para 'requests', añadirla rompe el build.
requirements = python3,kivy

# Optimizaciones para reducir tamano.
# IMPORTANTE: estas claves NO deben existir si estan vacias: buildozer convierte
# el valor vacio en [''] y emite --add-source '' / --add-asset <dir>:  lo que
# rompe p4a con FileExistsError: src/main/assets/
android.ignore_assets = yes

# Reducir arquitecturas (solo una para empezar)
# NO poner comentarios en la misma linea: buildozer los pasa como parte
# del valor y p4a falla con "storage dir path cannot contain spaces".
android.archs = arm64-v8a

# Permisos mínimos
android.permissions = INTERNET, REQUEST_INSTALL_PACKAGES

orientation = portrait
fullscreen = 0

# Logging reducido
log_level = 1

# Compresión
android.numeric_version = 116
android.gradle_repository = true

# Para reducir el tamaño del APK
# p4a 2026 exige NDK >= 25 (menor = error, mayor = warning). 25b es limpio.
android.ndk = 25b
android.minapi = 21

[buildozer]
log_level = 1
warn_on_root = 1