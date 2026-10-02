[app]
title = InDrive Finanzas
package.name = indrive_finanzas
package.domain = org.indrive
source.dir = .
source.include_exts = py,png,jpg,jpeg
version = 1.0.0

icon.filename = icon.png
presplash.filename = presplash.png

# La app solo usa la libreria estandar (urllib) para hablar con Supabase:
# python-for-android NO tiene receta para 'requests', añadirla rompe el build.
requirements = python3,kivy

# Optimizaciones para reducir tamaño
android.gradle_dependencies = 
android.add_src = 
android.add_assets = 
android.ignore_assets = yes

# Reducir arquitecturas (solo una para empezar)
# android.archs = arm64-v8a, armeabi-v7a  # Comenta esto
android.archs = arm64-v8a  # Solo una arquitectura

# Permisos mínimos
android.permissions = INTERNET

orientation = portrait
fullscreen = 0

# Logging reducido
log_level = 1

# Compresión
android.numeric_version = 1
android.gradle_repository = true

# Para reducir el tamaño del APK
android.ndk = 23c
android.sdk = 30
android.minapi = 21

[buildozer]
log_level = 1
warn_on_root = 1