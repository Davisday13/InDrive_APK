-- ============================================================
-- Análisis de COBRO POR KM — InDrive Finanzas (Supabase/PostgreSQL)
-- Ejecutar en: SQL Editor -> New query -> Run (rol owner, sin RLS)
-- Basado en: public.transacciones
--   Sesión de viaje: cuenta='Ahorro InDrive' AND categoria='Viaje InDrive' AND tipo='Ingreso'
--   Gasolina:        tipo='Gasto' AND categoria='Combustible'
--   Neto del conductor = monto - comision
-- ============================================================

-- ------------------------------------------------------------
-- 1. REVISIÓN DE LA BD (calidad de los datos)
--    Sin km > 0 no se puede calcular nada por km.
-- ------------------------------------------------------------
SELECT COUNT(*)                                   AS sesiones,
       SUM(CASE WHEN km > 0 THEN 1 ELSE 0 END)    AS con_km,
       SUM(CASE WHEN km = 0  THEN 1 ELSE 0 END)   AS sin_km,
       SUM(CASE WHEN comision > 0 THEN 1 ELSE 0 END) AS con_comision,
       MIN(fecha) AS primera, MAX(fecha) AS ultima
FROM public.transacciones
WHERE cuenta = 'Ahorro InDrive'
  AND categoria = 'Viaje InDrive'
  AND tipo = 'Ingreso';

-- ------------------------------------------------------------
-- 2. RESUMEN MENSUAL: $/km neto real (ya descontando gasolina)
--    Esta es la métrica que define si el cobro por km conviene.
-- ------------------------------------------------------------
WITH sesiones AS (
    SELECT substr(fecha, 1, 7) AS mes,
           SUM(monto)          AS bruto,
           SUM(comision)       AS comision,
           SUM(monto-comision) AS neto,
           SUM(km)             AS km,
           SUM(viajes)         AS viajes
    FROM public.transacciones
    WHERE cuenta = 'Ahorro InDrive'
      AND categoria = 'Viaje InDrive'
      AND tipo = 'Ingreso'
    GROUP BY 1
),
gas AS (
    SELECT substr(fecha, 1, 7) AS mes, SUM(monto) AS gasolina
    FROM public.transacciones
    WHERE tipo = 'Gasto' AND categoria = 'Combustible'
    GROUP BY 1
)
SELECT s.mes,
       ROUND(s.bruto, 2)      AS bruto,
       ROUND(s.comision, 2)   AS comision,
       ROUND(s.neto, 2)       AS neto,
       ROUND(s.km, 1)         AS km,
       s.viajes,
       ROUND(s.neto / NULLIF(s.km, 0), 2)                          AS neto_por_km,
       ROUND(COALESCE(g.gasolina, 0) / NULLIF(s.km, 0), 2)         AS gas_por_km,
       ROUND((s.neto - COALESCE(g.gasolina, 0)) / NULLIF(s.km,0),2) AS neto_menos_gas_por_km,
       ROUND(s.neto / NULLIF(s.viajes, 0), 2)                      AS neto_por_viaje,
       ROUND(s.km / NULLIF(s.viajes, 0), 2)                        AS km_por_viaje
FROM sesiones s
LEFT JOIN gas g ON g.mes = s.mes
ORDER BY s.mes;

-- ------------------------------------------------------------
-- 3. BENCHMARK: ¿cuánto cobro hoy por km? (mediana y percentiles)
--    p25 = cobras mal | mediana = lo normal | p75 = lo mejor
-- ------------------------------------------------------------
SELECT ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY (monto-comision)/km)::numeric, 2) AS p25_km,
       ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY (monto-comision)/km)::numeric, 2) AS mediana_km,
       ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY (monto-comision)/km)::numeric, 2) AS p75_km,
       ROUND(AVG((monto-comision)/km)::numeric, 2)                                         AS promedio_km,
       COUNT(*) AS sesiones
FROM public.transacciones
WHERE cuenta = 'Ahorro InDrive'
  AND categoria = 'Viaje InDrive'
  AND tipo = 'Ingreso'
  AND km > 0;

-- ------------------------------------------------------------
-- 4. TRAMOS DE DISTANCIA: dónde conviene subir la tarifa
--    Si un tramo tiene poco $/km, ese es el candidato a tarifa mínima.
-- ------------------------------------------------------------
SELECT CASE WHEN km <  3 THEN '1) 0-3 km (cortos)'
            WHEN km <  8 THEN '2) 3-8 km'
            WHEN km < 15 THEN '3) 8-15 km'
            ELSE              '4) 15+ km (largos)' END AS tramo,
       COUNT(*)                                   AS sesiones,
       ROUND(SUM(km), 1)                          AS km_totales,
       ROUND(AVG(km)::numeric, 2)                 AS km_promedio,
       ROUND(AVG((monto-comision)/km)::numeric, 2) AS dolar_prom_por_km,
       ROUND(MIN((monto-comision)/km)::numeric, 2) AS peor_km,
       ROUND(MAX((monto-comision)/km)::numeric, 2) AS mejor_km
FROM public.transacciones
WHERE cuenta = 'Ahorro InDrive'
  AND categoria = 'Viaje InDrive'
  AND tipo = 'Ingreso'
  AND km > 0
GROUP BY 1
ORDER BY 1;

-- ------------------------------------------------------------
-- 5. PEORES SESIONES POR $/km (aquí se pierde plata)
-- ------------------------------------------------------------
SELECT fecha,
       ROUND(monto, 2)      AS bruto,
       ROUND(comision, 2)   AS comision,
       km, viajes,
       ROUND((monto-comision) / km, 2)               AS neto_por_km,
       ROUND((monto-comision) / NULLIF(viajes,0), 2) AS neto_por_viaje,
       descripcion
FROM public.transacciones
WHERE cuenta = 'Ahorro InDrive'
  AND categoria = 'Viaje InDrive'
  AND tipo = 'Ingreso'
  AND km > 0
ORDER BY neto_por_km ASC
LIMIT 20;

-- ------------------------------------------------------------
-- 6. MEJOR DÍA PARA COBRAR MÁS (día de la semana)
-- ------------------------------------------------------------
SELECT CASE WHEN fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            THEN to_char(fecha::date, 'DY') ELSE 'S/F' END AS dia,
       COUNT(*) AS sesiones,
       ROUND(SUM(monto-comision), 2) AS neto,
       ROUND(SUM(km), 1) AS km,
       ROUND(AVG((monto-comision)/km)::numeric, 2) AS dolar_por_km
FROM public.transacciones
WHERE cuenta = 'Ahorro InDrive'
  AND categoria = 'Viaje InDrive'
  AND tipo = 'Ingreso'
  AND km > 0
GROUP BY 1
ORDER BY dolar_por_km DESC;

-- ------------------------------------------------------------
-- 7. SIMULADOR: ¿cuánto GANO EXTRA si subo el cobro a X $/km?
--    Cambia el valor de km_tarifa (ej. 0.60, 0.75, 1.00) y corre.
--    Muestra además cuántas sesiones quedan por debajo de la meta.
-- ------------------------------------------------------------
WITH meta AS (SELECT 0.75::numeric AS km_tarifa)
SELECT (SELECT km_tarifa FROM meta)                        AS tarifa_meta,
       COUNT(*)                                            AS sesiones_evaluadas,
       SUM(CASE WHEN (monto-comision)/km < (SELECT km_tarifa FROM meta)
                THEN 1 ELSE 0 END)                         AS sesiones_bajo_meta,
       ROUND(SUM(GREATEST((SELECT km_tarifa FROM meta)*km - (monto-comision), 0))::numeric, 2)
                                                           AS ganancia_extra_total,
       ROUND(AVG((monto-comision)/km)::numeric, 2)         AS dolar_actual_por_km
FROM public.transacciones
WHERE cuenta = 'Ahorro InDrive'
  AND categoria = 'Viaje InDrive'
  AND tipo = 'Ingreso'
  AND km > 0;

-- ------------------------------------------------------------
-- 8. META DE $/km FIJA POR LEY DE COSTOS
--    Piso real = costo gasolina/km + (mantenimiento+uso carro)/km
--    Cobrar por debajo de esto es perder plata en cada viaje.
-- ------------------------------------------------------------
WITH km_tot AS (
    SELECT SUM(km) AS km
    FROM public.transacciones
    WHERE cuenta = 'Ahorro InDrive' AND categoria = 'Viaje InDrive'
      AND tipo = 'Ingreso' AND km > 0
),
costos AS (
    SELECT SUM(CASE WHEN categoria = 'Combustible' THEN monto ELSE 0 END) AS gasolina,
           SUM(CASE WHEN tipo = 'Gasto' AND cuenta = 'Uso del Carro'
                    THEN monto ELSE 0 END) AS mantenimiento
    FROM public.transacciones
)
SELECT ROUND(k.km, 1) AS km_totales,
       ROUND(c.gasolina, 2) AS gasolina_total,
       ROUND(c.mantenimiento, 2) AS mantenimiento_total,
       ROUND(c.gasolina / NULLIF(k.km, 0), 2) AS costo_gas_por_km,
       ROUND((c.gasolina + c.mantenimiento) / NULLIF(k.km, 0), 2) AS costo_total_por_km
FROM km_tot k, costos c;

-- ------------------------------------------------------------
-- 9. (SQLite / local) mismo análisis para la app en PC:
--    python -c "import sqlite3; ..."  o DB Browser
-- ------------------------------------------------------------
-- SELECT substr(fecha,1,7) mes,
--        ROUND(SUM(monto-comision)/NULLIF(SUM(km),0),2) AS neto_por_km,
--        SUM(km) km, SUM(viajes) viajes
-- FROM transacciones
-- WHERE cuenta='Ahorro InDrive' AND categoria='Viaje InDrive'
--   AND tipo='Ingreso'
-- GROUP BY 1 ORDER BY 1;
