# 📱 InDrive Finanzas

App Android para gestionar las finanzas personales de un conductor InDrive.  
Desarrollada con **Python + Kivy**.

## ✨ Funcionalidades

- 💰 **Ahorros InDrive** – Registro de viajes e ingresos netos
- 🚗 **Fondo del Carro** – Control de gastos e ingresos del vehículo
- 🏠 **Alquiler Casa** – Gestión de pagos de alquiler y tasas de aseo
- 📅 **Calendario** – Vista diaria de movimientos
- 📊 **Estadísticas** – Resúmenes mensuales y comparativos

## 📲 Descargar el APK

Ve a la pestaña **[Actions](../../actions)** → selecciona la última ejecución exitosa → descarga el artifact `InDrive-Finanzas-APK`.

## 🛠️ Ejecutar en PC (desarrollo)

```bash
pip install kivy
python main.py
```

## 🏗️ Compilar APK manualmente (requiere Linux)

```bash
pip install buildozer
buildozer android debug
```

El APK quedará en la carpeta `bin/`.

## 📁 Estructura

```
InDrive_APK/
├── main.py              # Código principal de la app
├── buildozer.spec       # Configuración de compilación Android
├── indrive_finanzas.db  # Base de datos SQLite
├── icon.png             # Ícono de la app
└── presplash.png        # Pantalla de carga
```

## 📄 Licencia

Proyecto académico – Programación III.
