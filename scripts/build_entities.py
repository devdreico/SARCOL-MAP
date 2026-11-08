#!/usr/bin/env python3
"""Construye el atlas de entidades de SARCOL MAP.

Fuentes:
  - MinTIC / SIGEP: directorio georreferenciado de entidades públicas.
  - SIGEP II: nómina y naturaleza jurídica (enriquecimiento por nombre).
  - Supersociedades: 10.000 empresas con mayores ingresos, corte 2025.
  - DIVIPOLA: centroides municipales para geocodificación aproximada.
  - Curaduría propia: entidades estratégicas, gremios, medios, partidos,
    universidades, infraestructura y actores internacionales.

El resultado es un archivo de 5.000 fichas y una capa GeoJSON mínima para el mapa.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CURATED = ROOT / "data" / "curated"
OUT = ROOT / "public" / "data"
TODAY = "2026-10-27"

PUBLIC_TARGET = 3800
PRIVATE_TARGET = 1000
TOTAL_TARGET = 5000

SOURCE_MINTIC = {
    "name": "MinTIC / SIGEP — directorio georreferenciado de entidades",
    "url": "https://www.datos.gov.co/Organizaci-n-Institucional/Directorio-de-entidades-del-Estado-colombiano/kqut-4h4r",
    "date": "2026",
    "license": "Datos abiertos",
}
SOURCE_SIGEP = {
    "name": "SIGEP II — empleo público",
    "url": "https://www.datos.gov.co/Funci-n-P-blica/SIGEP-II/h8rs-jxum",
    "date": "2026",
    "license": "Datos abiertos",
}
SOURCE_SUPERSOC = {
    "name": "Superintendencia de Sociedades — 10.000 empresas",
    "url": "https://www.datos.gov.co/Econom-a-y-Finanzas/10-000-empresas/6cat-2gcs",
    "date": "2025",
    "license": "Datos abiertos",
}
SOURCE_DIVIPOLA = {
    "name": "DANE — DIVIPOLA",
    "url": "https://www.datos.gov.co/Estad-sticas/DIVIPOLA/gdxc-w37w",
    "date": "2025",
    "license": "Datos abiertos",
}

STATE_COMPANIES = {
    "ECOPETROL",
    "ISA",
    "INTERCONEXION ELECTRICA",
    "BANCO AGRARIO",
    "BANCOLDEX",
    "FINDETER",
    "FONDO NACIONAL DEL AHORRO",
    "FNA",
    "SATENA",
    "INDUMIL",
    "4 72",
    "RTVC",
    "SOCIEDAD TELEVISORA DE COLOMBIA",
    "SERVICIO POSTAL NACIONAL",
    "EMPRESAS PUBLICAS DE MEDELLIN",
    "EPM",
    "EMPRESAS MUNICIPALES DE CALI",
    "EMCALI",
    "EMPRESA DE ACUEDUCTO Y ALCANTARILLADO DE BOGOTA",
    "EAAB",
    "EMPRESA DE ENERGIA DE BOGOTA",
    "EEB",
    "EMPRESA DE TELECOMUNICACIONES DE BOGOTA",
    "ETB",
    "ISAGEN",
    "XM",
    "CENIT",
    "CISA",
    "CENTRAL HIDROELECTRICA DE CALDAS",
    "CHEC",
    "URRÁ",
    "URRA",
    "GECELCA",
    "AIR E",
    "AFINIA",
    "FIDUCIARIA LA PREVISORA",
    "FIDUPREVISORA",
    "FONDO DE GARANTIAS DE INSTITUCIONES FINANCIERAS",
    "FOGAFIN",
    "FOGACOOP",
    "FINAGRO",
    "FONDO PARA EL FINANCIAMIENTO DEL SECTOR AGROPECUARIO",
    "ICETEX",
    "FONDO NACIONAL DE GARANTIAS",
    "FNG",
    "SENA",
    "SERVICIO NACIONAL DE APRENDIZAJE",
    "UNIVERSIDAD NACIONAL",
    "UNAD",
    "ICEETEX",
    "FIDUCIARIA CENTRAL",
    "FIDUCIARIA POPULAR",
    "FIDUCIARIA BANCOLOMBIA",
}

# Descripciones y claves de lectura para entidades visibles. Se aplican por
# nombre normalizado; el resto recibe una ficha generada a partir de su tipo,
# nivel y sector. No se inventan acusaciones ni relaciones.
KNOWN: dict[str, dict] = {
    "PRESIDENCIA DE LA REPUBLICA": {
        "description": "Sede del Gobierno Nacional y de la Presidencia de la República. Desde aquí se dirige la administración pública, se nombran ministros y se define la agenda legislativa y de política exterior. Es el nodo formal más visible del poder ejecutivo colombiano.",
        "functions": "Dirección política del Estado, coordinación del gabinete, relaciones exteriores, planeación nacional y ejecución de políticas públicas.",
        "power_note": "Poder político formal por dirección del Gobierno Nacional; su capacidad real depende de coaliciones, Congreso y capacidad administrativa.",
        "tags": ["gobierno", "ejecutivo", "presidencia"],
    },
    "CASA DE NARINO": {
        "description": "Residencia y despacho oficial del Presidente de la República. Sede de reuniones de alto nivel, consejos de ministros y recepción de jefes de Estado.",
        "functions": "Sede protocoloaria y operativa de la Presidencia de la República.",
        "power_note": "Símbolo y centro operativo del poder ejecutivo nacional.",
        "tags": ["gobierno", "ejecutivo", "presidencia"],
    },
    "CONGRESO DE LA REPUBLICA": {
        "description": "Sede del Senado y la Cámara de Representantes. Aprueba leyes, reformas constitucionales, presupuesto y tratados; ejerce control político sobre el Gobierno y elige altos cargos.",
        "functions": "Legislación, control político, aprobación presupuestal y representación territorial.",
        "power_note": "Poder legislativo formal; su influencia depende de bancadas, coaliciones y agenda de reformas.",
        "tags": ["gobierno", "legislativo", "congreso"],
    },
    "SENADO DE LA REPUBLICA": {
        "description": "Cámara alta del Congreso. Representa a la Nación, aprueba leyes y reformas, ejerce control político y participa en la elección de altos funcionarios.",
        "functions": "Legislación nacional, control político y representación territorial.",
        "tags": ["gobierno", "legislativo"],
    },
    "CAMARA DE REPRESENTANTES": {
        "description": "Cámara baja del Congreso. Representa a los departamentos y distritos; tramita leyes, presupuesto y control político.",
        "functions": "Legislación, control político y representación territorial.",
        "tags": ["gobierno", "legislativo"],
    },
    "CORTE CONSTITUCIONAL": {
        "description": "Guardián de la Constitución de 1991. Decide tutelas, demandas de inconstitucionalidad y conflictos de competencias; sus sentencias tienen efectos sobre todo el ordenamiento jurídico.",
        "functions": "Control de constitucionalidad, revisión de tutelas y resolución de conflictos institucionales.",
        "power_note": "Poder jurídico de cierre; sus decisiones pueden invalidar leyes y políticas.",
        "tags": ["gobierno", "judicial", "alta corte"],
    },
    "CORTE SUPREMA DE JUSTICIA": {
        "description": "Máximo tribunal de la jurisdicción ordinaria. Decide casación, extradición y procesos de alto impacto; interpreta el derecho penal, civil, laboral y de familia.",
        "functions": "Casación, unificación de jurisprudencia y juzgamiento de altos funcionarios.",
        "tags": ["gobierno", "judicial", "alta corte"],
    },
    "CONSEJO DE ESTADO": {
        "description": "Máximo tribunal de la jurisdicción de lo contencioso administrativo. Controla la legalidad de actos administrativos y resuelve conflictos entre el Estado y los particulares.",
        "functions": "Control de legalidad, nulidades, reparación directa y consulta de actos administrativos.",
        "tags": ["gobierno", "judicial", "alta corte"],
    },
    "FISCALIA GENERAL DE LA NACION": {
        "description": "Dirige la investigación penal y ejerce la acción penal. Su autonomía y capacidad investigativa son centrales para el acceso a la justicia y la lucha contra la impunidad.",
        "functions": "Investigación penal, acusación, protección a víctimas y articulación con la policía judicial.",
        "tags": ["gobierno", "justicia", "fiscalia"],
    },
    "PROCURADURIA GENERAL DE LA NACION": {
        "description": "Ministerio Público. Vigila la conducta de servidores públicos, interviene en procesos disciplinarios y protege derechos humanos y ambientales.",
        "functions": "Control disciplinario, vigilancia administrativa y defensa del ordenamiento jurídico.",
        "tags": ["gobierno", "control", "ministerio publico"],
    },
    "CONTRALORIA GENERAL DE LA REPUBLICA": {
        "description": "Máximo órgano de control fiscal. Audita el manejo de recursos públicos y puede iniciar procesos de responsabilidad fiscal.",
        "functions": "Control fiscal, auditoría y responsabilidad fiscal.",
        "tags": ["gobierno", "control", "fiscal"],
    },
    "DEFENSORIA DEL PUEBLO": {
        "description": "Institución del Ministerio Público encargada de proteger los derechos humanos, atender quejas y acompañar a víctimas.",
        "functions": "Defensa de derechos humanos, prevención de violaciones y acompañamiento a víctimas.",
        "tags": ["gobierno", "derechos humanos", "control"],
    },
    "REGISTRADURIA NACIONAL DEL ESTADO CIVIL": {
        "description": "Organiza elecciones, administra el registro civil y expide documentos de identidad. Es una pieza central de la infraestructura democrática.",
        "functions": "Organización electoral, identificación y registro civil.",
        "tags": ["gobierno", "electoral"],
    },
    "CONSEJO NACIONAL ELECTORAL": {
        "description": "Autoridad electoral administrativa. Vigila partidos, campañas y escrutinios; puede sancionar y decidir sobre personerías jurídicas.",
        "functions": "Inspección y vigilancia electoral, escrutinios y regulación de partidos.",
        "tags": ["gobierno", "electoral"],
    },
    "JURISDICCION ESPECIAL PARA LA PAZ": {
        "description": "Jurisdicción transicional creada por el Acuerdo de Paz de 2016. Investiga, juzga y sanciona graves crímenes del conflicto armado.",
        "functions": "Justicia transicional, verdad, reparación y garantías de no repetición.",
        "tags": ["gobierno", "justicia transicional", "paz"],
    },
    "UNIDAD DE BUSQUEDA DE PERSONAS DADAS POR DESAPARECIDAS": {
        "description": "Entidad extrajudicial que busca a personas desaparecidas en el contexto del conflicto armado y articula acciones con familias y autoridades.",
        "functions": "Búsqueda humanitaria, identificación y acompañamiento a familias.",
        "tags": ["gobierno", "derechos humanos", "paz"],
    },
    "AGENCIA NACIONAL DE TIERRAS": {
        "description": "Administra tierras de la Nación, impulsa la formalización y la adjudicación, y gestiona el Fondo de Tierras para la reforma agraria.",
        "functions": "Ordenamiento social de la propiedad, formalización, adjudicación y gestión de tierras.",
        "tags": ["gobierno", "tierras", "rural"],
    },
    "AGENCIA NACIONAL DE MINERIA": {
        "description": "Administra el catastro minero y otorga títulos mineros. Su gestión define quién puede explorar y explotar minerales en el país.",
        "functions": "Titulación minera, catastro, fiscalización y recaudo de regalías.",
        "tags": ["gobierno", "mineria", "extractivas"],
    },
    "AGENCIA NACIONAL DE HIDROCARBUROS": {
        "description": "Administra los recursos hidrocarburíferos de la Nación, asigna áreas y regula contratos de exploración y producción.",
        "functions": "Asignación de áreas, contratos, seguimiento y participación estatal en hidrocarburos.",
        "tags": ["gobierno", "hidrocarburos", "extractivas"],
    },
    "AUTORIDAD NACIONAL DE LICENCIAS AMBIENTALES": {
        "description": "Evalúa y otorga licencias ambientales para proyectos de gran escala. Sus decisiones condicionan la viabilidad de minería, energía e infraestructura.",
        "functions": "Licenciamiento ambiental, seguimiento y control de proyectos estratégicos.",
        "tags": ["gobierno", "ambiente", "licencias"],
    },
    "AGENCIA NACIONAL DE INFRAESTRUCTURA": {
        "description": "Estructura y ejecuta concesiones de infraestructura vial, férrea, portuaria y aeroportuaria. Es un nodo clave entre el Estado y los grandes contratistas.",
        "functions": "Concesiones, asociaciones público-privadas y seguimiento de infraestructura.",
        "tags": ["gobierno", "infraestructura", "concesiones"],
    },
    "DIRECCION DE IMPUESTOS Y ADUANAS NACIONALES": {
        "description": "Administra impuestos, aduanas y control cambiario. Define buena parte de los ingresos del Estado y la trazabilidad del comercio exterior.",
        "functions": "Recaudo tributario, aduanas, fiscalización y control al comercio exterior.",
        "tags": ["gobierno", "hacienda", "tributario"],
    },
    "DEPARTAMENTO ADMINISTRATIVO NACIONAL DE ESTADISTICA": {
        "description": "Produce las estadísticas oficiales de Colombia, incluyendo inflación, empleo, pobreza, censos y cuentas nacionales.",
        "functions": "Producción estadística, censos, indicadores económicos y sociales.",
        "tags": ["gobierno", "estadistica", "datos"],
    },
    "BANCO DE LA REPUBLICA": {
        "description": "Banco central. Define la política monetaria, controla la inflación, administra reservas internacionales y emite moneda.",
        "functions": "Política monetaria, estabilidad de precios, reservas y sistema de pagos.",
        "tags": ["gobierno", "monetario", "banco central"],
    },
    "ECOPETROL": {
        "description": "Principal empresa de hidrocarburos de Colombia y una de las mayores del país. Opera exploración, producción, refinación y transporte; el Estado conserva una participación mayoritaria.",
        "functions": "Exploración, producción, refinación, transporte y comercialización de hidrocarburos.",
        "power_note": "Poder económico y territorial por ingresos, infraestructura y presencia en regiones extractivas; su gobernanza combina Estado y mercado.",
        "ownership": "Estado 88,49%",
        "tags": ["empresa", "hidrocarburos", "extractivas", "estado"],
    },
    "CERREJON": {
        "description": "Operación de carbón a cielo abierto en La Guajira, una de las mayores minas de carbón de América Latina. Su operación ha estado rodeada de debates sobre agua, territorio, derechos humanos y transición energética.",
        "functions": "Extracción, transporte y exportación de carbón térmico.",
        "power_note": "Poder económico y territorial en La Guajira; su licencia social y ambiental es objeto de escrutinio público.",
        "tags": ["empresa", "mineria", "carbon", "extractivas"],
    },
    "DRUMMOND": {
        "description": "Productor de carbón en el Cesar, con minas y puerto propio en el Caribe. Es uno de los mayores exportadores de carbón del país.",
        "functions": "Extracción, transporte y exportación de carbón.",
        "power_note": "Poder económico regional y vínculos con infraestructura portuaria y ferroviaria.",
        "tags": ["empresa", "mineria", "carbon", "extractivas"],
    },
    "CERRO MATOSO": {
        "description": "Mina de ferroníquel en Córdoba, operada por South32. Es uno de los principales productores de níquel de América Latina.",
        "functions": "Extracción y procesamiento de níquel.",
        "power_note": "Poder económico regional y presión sobre territorio, agua y comunidades.",
        "tags": ["empresa", "mineria", "niquel", "extractivas"],
    },
    "GRUPO AVAL": {
        "description": "Holding financiero controlado por la familia Sarmiento Angulo. Agrupa bancos, aseguradoras y fiduciarias con presencia nacional.",
        "functions": "Banca, seguros, fiducia y servicios financieros.",
        "power_note": "Poder económico por concentración del crédito y capacidad de influir en la agenda financiera.",
        "tags": ["empresa", "finanzas", "grupo economico"],
    },
    "GRUPO BOLIVAR": {
        "description": "Holding financiero y de servicios. Controla Banco Davivienda, Seguros Bolívar y otras compañías.",
        "functions": "Banca, seguros, vivienda y servicios financieros.",
        "power_note": "Poder económico por participación en el crédito hipotecario y los seguros.",
        "tags": ["empresa", "finanzas", "grupo economico"],
    },
    "GRUPO EMPRESARIAL ANTIOQUENO": {
        "description": "Red de empresas antioqueñas con participación cruzada en alimentos, cemento, energía y servicios financieros. Incluye Sura, Argos, Nutresa y Bancolombia.",
        "functions": "Inversión y coordinación de empresas en alimentos, infraestructura, energía y finanzas.",
        "power_note": "Poder económico regional y nacional; su estructura de propiedad cruzada es relevante para el análisis de competencia.",
        "tags": ["empresa", "grupo economico", "antioquia"],
    },
    "BANCOLOMBIA": {
        "description": "Mayor banco privado de Colombia por activos. Hace parte del Grupo Empresarial Antioqueño y tiene presencia en banca personal, empresarial e inversión.",
        "functions": "Crédito, depósitos, inversión y servicios financieros.",
        "power_note": "Poder económico por tamaño, red de sucursales y financiamiento empresarial.",
        "tags": ["empresa", "finanzas", "banca"],
    },
    "DAVIVIENDA": {
        "description": "Banco del Grupo Bolívar, con fuerte presencia en crédito hipotecario y banca personal.",
        "functions": "Crédito hipotecario, banca personal y empresarial.",
        "tags": ["empresa", "finanzas", "banca"],
    },
    "BANCO DE BOGOTA": {
        "description": "Banco del Grupo Aval, uno de los mayores del país por activos y red de oficinas.",
        "functions": "Banca comercial, crédito y servicios financieros.",
        "tags": ["empresa", "finanzas", "banca"],
    },
    "ORGANIZACION ARDILA LULLE": {
        "description": "Grupo empresarial con presencia en medios, bebidas, textiles, azúcar y energía. Es uno de los conglomerados familiares más importantes de Colombia.",
        "functions": "Inversión en medios, industria, agroindustria y energía.",
        "power_note": "Poder económico y mediático; su influencia cruza negocios, opinión pública y política.",
        "tags": ["empresa", "grupo economico", "medios"],
    },
    "GRUPO SANTO DOMINGO": {
        "description": "Conglomerado con inversiones en medios, infraestructura, energía y cemento. Incluye activos como Caracol Televisión y El Espectador.",
        "functions": "Inversión en medios, infraestructura, energía y servicios.",
        "power_note": "Poder económico y capacidad de incidencia en la opinión pública.",
        "tags": ["empresa", "grupo economico", "medios"],
    },
    "ANDI": {
        "description": "Asociación Nacional de Empresarios de Colombia. Principal gremio industrial; participa en debates de política económica, tributaria, comercial y laboral.",
        "functions": "Representación empresarial, cabildeo y producción de propuestas de política pública.",
        "power_note": "Poder de agenda y articulación empresarial; no es una entidad estatal.",
        "tags": ["gremio", "empresarios", "industria"],
    },
    "FENALCO": {
        "description": "Federación Nacional de Comerciantes. Representa al comercio y participa en debates sobre tributación, formalización y política comercial.",
        "functions": "Representación gremial, capacitación y análisis del comercio.",
        "tags": ["gremio", "comercio"],
    },
    "SOCIEDAD DE AGRICULTORES DE COLOMBIA": {
        "description": "Gremio histórico del sector agropecuario. Participa en la agenda rural, tierras, comercio agropecuario y política agrícola.",
        "functions": "Representación de agricultores y cabildeo sectorial.",
        "tags": ["gremio", "agro", "rural"],
    },
    "ASOBANCARIA": {
        "description": "Asociación de bancos de Colombia. Agrupa a la banca privada y participa en la regulación financiera, el crédito y la inclusión financiera.",
        "functions": "Representación del sector bancario y análisis regulatorio.",
        "tags": ["gremio", "finanzas", "banca"],
    },
    "ASOCIACION COLOMBIANA DE PETROLEOS": {
        "description": "Gremio del sector de hidrocarburos. Promueve la inversión, la exploración y la producción; participa en debates sobre transición energética.",
        "functions": "Representación sectorial, análisis y cabildeo en hidrocarburos.",
        "tags": ["gremio", "hidrocarburos", "extractivas"],
    },
    "FEDEGAN": {
        "description": "Federación Colombiana de Ganaderos. Representa al sector ganadero y participa en políticas de tierras, sanidad, comercio y desarrollo rural.",
        "functions": "Representación ganadera, sanidad animal y política rural.",
        "tags": ["gremio", "ganaderia", "rural"],
    },
    "ASOCANA": {
        "description": "Asociación de cultivadores de caña de azúcar. Representa al complejo agroindustrial del Valle del Cauca.",
        "functions": "Representación del sector cañicultor y análisis agroindustrial.",
        "tags": ["gremio", "agroindustria", "valle"],
    },
    "CAMARA COLOMBIANA DE LA INFRAESTRUCTURA": {
        "description": "Gremio de la infraestructura. Reúne constructoras, concesionarios y consultores; participa en la agenda de obra pública y APP.",
        "functions": "Representación del sector infraestructura y cabildeo.",
        "tags": ["gremio", "infraestructura", "construccion"],
    },
    "EL TIEMPO": {
        "description": "Uno de los periódicos de referencia de Colombia. Su cobertura incide en la agenda política y económica.",
        "functions": "Periodismo, investigación y opinión pública.",
        "power_note": "Poder de agenda y opinión; no equivale a poder estatal.",
        "tags": ["medio", "prensa"],
    },
    "EL ESPECTADOR": {
        "description": "Periódico de circulación nacional con tradición de periodismo político y judicial.",
        "functions": "Periodismo, investigación y opinión.",
        "tags": ["medio", "prensa"],
    },
    "SEMANA": {
        "description": "Revista de análisis político y actualidad. Ha tenido un papel central en la agenda pública y en la investigación periodística.",
        "functions": "Periodismo de análisis, investigación y opinión.",
        "tags": ["medio", "revista"],
    },
    "LA SILLA VACIA": {
        "description": "Medio digital especializado en poder, política y conflicto. Es referencia para el análisis de élites y toma de decisiones.",
        "functions": "Periodismo político, análisis y verificación.",
        "tags": ["medio", "digital", "politica"],
    },
    "CARACOL TELEVISION": {
        "description": "Principal canal privado de televisión abierta. Su alcance masivo lo convierte en un actor central de la opinión pública.",
        "functions": "Televisión, noticias y entretenimiento.",
        "tags": ["medio", "television"],
    },
    "RCN TELEVISION": {
        "description": "Canal privado de televisión abierta con presencia nacional e internacional.",
        "functions": "Televisión, noticias y entretenimiento.",
        "tags": ["medio", "television"],
    },
    "UNIVERSIDAD NACIONAL DE COLOMBIA": {
        "description": "Principal universidad pública del país. Forma profesionales e investigadores y produce conocimiento en ciencias, ingenierías, salud y ciencias sociales.",
        "functions": "Docencia, investigación y extensión.",
        "tags": ["universidad", "educacion", "publica"],
    },
    "UNIVERSIDAD DE LOS ANDES": {
        "description": "Universidad privada de referencia en ciencias sociales, economía, derecho e ingeniería. Influye en debates públicos y formación de élites.",
        "functions": "Docencia, investigación y extensión.",
        "tags": ["universidad", "educacion", "privada"],
    },
    "PONTIFICIA UNIVERSIDAD JAVERIANA": {
        "description": "Universidad privada jesuita con presencia nacional. Destaca en salud, derecho, ciencias sociales e ingeniería.",
        "functions": "Docencia, investigación y extensión.",
        "tags": ["universidad", "educacion", "privada"],
    },
    "FEDESARROLLO": {
        "description": "Centro de investigación económica y social. Produce análisis y propuestas sobre política fiscal, mercado laboral, pobreza y desarrollo.",
        "functions": "Investigación aplicada y incidencia en política pública.",
        "tags": ["think tank", "economia", "politica publica"],
    },
    "DEJUSTICIA": {
        "description": "Centro de estudios jurídicos y sociales. Trabaja en derechos humanos, justicia, tierras, género y política de drogas.",
        "functions": "Investigación, litigio estratégico e incidencia.",
        "tags": ["think tank", "derechos humanos", "justicia"],
    },
    "INDEPAZ": {
        "description": "Instituto de estudios para el desarrollo y la paz. Documenta conflicto armado, liderazgos sociales y economías ilícitas.",
        "functions": "Investigación, monitoreo y acompañamiento a procesos de paz.",
        "tags": ["think tank", "paz", "conflicto"],
    },
    "PARES": {
        "description": "Fundación Paz y Reconciliación. Analiza conflicto armado, economías ilegales, política y dinámicas territoriales.",
        "functions": "Investigación y análisis de conflicto y paz.",
        "tags": ["think tank", "paz", "conflicto"],
    },
    "FLIP": {
        "description": "Fundación para la Libertad de Prensa. Monitorea amenazas a periodistas y defensa la libertad de expresión.",
        "functions": "Monitoreo, protección y incidencia por la libertad de prensa.",
        "tags": ["ong", "prensa", "derechos humanos"],
    },
    "WWF COLOMBIA": {
        "description": "Organización conservacionista con presencia en ecosistemas estratégicos. Trabaja en conservación, políticas ambientales y territorios sostenibles.",
        "functions": "Conservación, investigación y incidencia ambiental.",
        "tags": ["ong", "ambiente", "conservacion"],
    },
    "COMISION COLOMBIANA DE JURISTAS": {
        "description": "Organización de derechos humanos con trabajo en justicia, conflicto armado, memoria y reparación.",
        "functions": "Litigio, investigación y acompañamiento a víctimas.",
        "tags": ["ong", "derechos humanos", "justicia"],
    },
    "CENTRO NACIONAL DE MEMORIA HISTORICA": {
        "description": "Entidad pública que documenta el conflicto armado, produce memoria histórica y acompaña a víctimas.",
        "functions": "Investigación histórica, memoria y reparación simbólica.",
        "tags": ["gobierno", "memoria", "derechos humanos"],
    },
    "ORGANIZACION DE LAS NACIONES UNIDAS": {
        "description": "Sistema de Naciones Unidas en Colombia. Articula agencias en paz, derechos humanos, desarrollo, ayuda humanitaria y verificación.",
        "functions": "Cooperación internacional, asistencia humanitaria y acompañamiento a la paz.",
        "tags": ["internacional", "onu", "cooperacion"],
    },
    "PROGRAMA DE LAS NACIONES UNIDAS PARA EL DESARROLLO": {
        "description": "Agencia de la ONU para el desarrollo. Apoya gobernabilidad, paz, reducción de pobreza y desarrollo territorial.",
        "functions": "Cooperación técnica, programas de desarrollo y acompañamiento institucional.",
        "tags": ["internacional", "onu", "desarrollo"],
    },
    "BANCO MUNDIAL": {
        "description": "Institución financiera multilateral. Financia proyectos de desarrollo y produce conocimiento sobre economía y política pública.",
        "functions": "Financiamiento, asistencia técnica e investigación.",
        "tags": ["internacional", "multilateral", "finanzas"],
    },
    "BANCO INTERAMERICANO DE DESARROLLO": {
        "description": "Banco multilateral de desarrollo para América Latina y el Caribe. Financia infraestructura, Estado y programas sociales.",
        "functions": "Financiamiento y asistencia técnica.",
        "tags": ["internacional", "multilateral", "finanzas"],
    },
    "UNION EUROPEA": {
        "description": "Delegación de la Unión Europea en Colombia. Financia cooperación, paz, derechos humanos y transición verde.",
        "functions": "Cooperación internacional, diplomacia y financiamiento.",
        "tags": ["internacional", "europa", "cooperacion"],
    },
    "USAID": {
        "description": "Agencia de cooperación de Estados Unidos. Financia programas de desarrollo, gobernabilidad, paz y ayuda humanitaria.",
        "functions": "Cooperación internacional y asistencia técnica.",
        "tags": ["internacional", "eeuu", "cooperacion"],
    },
    "CENTRO DEMOCRATICO": {
        "description": "Partido político de centro-derecha. Ha tenido un papel central en la política colombiana de las últimas dos décadas.",
        "functions": "Representación política, formulación de programa y competencia electoral.",
        "power_note": "Poder político por bancadas, gobierno y capacidad de movilización; no es una entidad estatal.",
        "tags": ["partido", "politica"],
    },
    "PACTO HISTORICO": {
        "description": "Coalición política de izquierda y centroizquierda que llegó al Gobierno en 2022. Agrupa partidos y movimientos sociales.",
        "functions": "Coalición electoral y política; coordinación programática.",
        "power_note": "Poder político por control del Ejecutivo y bancadas; coalición heterogénea.",
        "tags": ["partido", "politica", "coalicion"],
    },
    "PARTIDO LIBERAL COLOMBIANO": {
        "description": "Partido histórico colombiano de centro. Ha participado en gobiernos y coaliciones durante más de un siglo.",
        "functions": "Representación política y competencia electoral.",
        "tags": ["partido", "politica"],
    },
    "PARTIDO CONSERVADOR COLOMBIANO": {
        "description": "Partido histórico de centro-derecha. Ha sido actor central en la política colombiana desde el siglo XIX.",
        "functions": "Representación política y competencia electoral.",
        "tags": ["partido", "politica"],
    },
    "CAMBIO RADICAL": {
        "description": "Partido de centro-derecha con presencia nacional. Ha participado en coaliciones de gobierno y en la agenda legislativa.",
        "functions": "Representación política y competencia electoral.",
        "tags": ["partido", "politica"],
    },
    "ALIANZA VERDE": {
        "description": "Partido de centro y centroizquierda con agenda ambiental, descentralización y derechos.",
        "functions": "Representación política y competencia electoral.",
        "tags": ["partido", "politica", "ambiente"],
    },
    "CENTRAL HIDROELECTRICA DE GUAVIO": {
        "description": "Central hidroeléctrica en Cundinamarca. Aporta energía al sistema interconectado y forma parte de la infraestructura crítica del país.",
        "functions": "Generación hidroeléctrica.",
        "tags": ["infraestructura", "energia", "hidroelectrica"],
    },
    "HIDROITUANGO": {
        "description": "Megaproyecto hidroeléctrico en Antioquia, desarrollado por EPM. Es la mayor central del país y ha tenido impactos técnicos, ambientales y sociales de gran escala.",
        "functions": "Generación hidroeléctrica y regulación del río Cauca.",
        "power_note": "Infraestructura crítica con efectos regionales sobre energía, agua y territorio.",
        "tags": ["infraestructura", "energia", "hidroelectrica", "antioquia"],
    },
    "REFINERIA DE CARTAGENA": {
        "description": "Complejo de refinación de Ecopetrol en Cartagena. Procesa crudo y produce combustibles para el mercado nacional y de exportación.",
        "functions": "Refinación de hidrocarburos.",
        "tags": ["infraestructura", "energia", "hidrocarburos"],
    },
    "REFINERIA DE BARRANCABERMEJA": {
        "description": "Complejo industrial de Ecopetrol en Santander. Es una pieza central del abastecimiento de combustibles y petroquímica.",
        "functions": "Refinación, petroquímica y logística de hidrocarburos.",
        "tags": ["infraestructura", "energia", "hidrocarburos"],
    },
    "PUERTO DE BUENAVENTURA": {
        "description": "Principal puerto marítimo de carga del Pacífico colombiano. Conecta el comercio exterior con Asia y el Pacífico.",
        "functions": "Operación portuaria, logística y comercio exterior.",
        "tags": ["infraestructura", "puerto", "logistica"],
    },
    "PUERTO DE CARTAGENA": {
        "description": "Uno de los principales nodos portuarios del Caribe colombiano, con terminales de contenedores y carga general.",
        "functions": "Operación portuaria y logística internacional.",
        "tags": ["infraestructura", "puerto", "logistica"],
    },
    "PUERTO DE BARRANQUILLA": {
        "description": "Puerto fluviomarítimo sobre el río Magdalena. Conecta el interior del país con el Caribe.",
        "functions": "Operación portuaria y transporte fluvial.",
        "tags": ["infraestructura", "puerto", "logistica"],
    },
    "PUERTO DE SANTA MARTA": {
        "description": "Terminal portuario del Caribe con operación de carga y cruceros. Es un nodo logístico regional.",
        "functions": "Operación portuaria y turismo.",
        "tags": ["infraestructura", "puerto", "logistica"],
    },
    "AEROPUERTO EL DORADO": {
        "description": "Principal aeropuerto de Colombia y uno de los mayores de América Latina. Concentra el tráfico nacional e internacional.",
        "functions": "Transporte aéreo de pasajeros y carga.",
        "tags": ["infraestructura", "aeropuerto", "transporte"],
    },
    "AEROPUERTO JOSE MARIA CORDOVA": {
        "description": "Aeropuerto internacional que sirve a Medellín y al Valle de Aburrá.",
        "functions": "Transporte aéreo de pasajeros y carga.",
        "tags": ["infraestructura", "aeropuerto", "transporte"],
    },
    "AEROPUERTO ALFONSO BONILLA ARAGON": {
        "description": "Aeropuerto internacional que sirve a Cali y al suroccidente colombiano.",
        "functions": "Transporte aéreo de pasajeros y carga.",
        "tags": ["infraestructura", "aeropuerto", "transporte"],
    },
    "AEROPUERTO ERNESTO CORTISSOZ": {
        "description": "Aeropuerto internacional de Barranquilla y del Atlántico.",
        "functions": "Transporte aéreo de pasajeros y carga.",
        "tags": ["infraestructura", "aeropuerto", "transporte"],
    },
    "AEROPUERTO RAFAEL NUNEZ": {
        "description": "Aeropuerto internacional de Cartagena, con fuerte componente turístico.",
        "functions": "Transporte aéreo de pasajeros y carga.",
        "tags": ["infraestructura", "aeropuerto", "transporte"],
    },
    "BASE MILITAR DE TOLEMAIDA": {
        "description": "Una de las principales instalaciones de entrenamiento y operación del Ejército Nacional. Concentra unidades de fuerzas especiales y aviación del Ejército.",
        "functions": "Entrenamiento, operaciones militares y logística.",
        "tags": ["infraestructura", "defensa", "militar"],
    },
    "BASE AEREA DE CATAM": {
        "description": "Instalación de la Fuerza Aérea Colombiana en Cundinamarca. Opera transporte estratégico y unidades de combate.",
        "functions": "Operaciones aéreas militares y logística.",
        "tags": ["infraestructura", "defensa", "militar"],
    },
    "BASE AEREA DE APIAY": {
        "description": "Base de la Fuerza Aérea Colombiana en Villavicencio. Tiene un papel central en la proyección hacia los Llanos y la Amazonia.",
        "functions": "Operaciones aéreas, transporte y entrenamiento.",
        "tags": ["infraestructura", "defensa", "militar"],
    },
    "BASE NAVAL BAHIA MALAGA": {
        "description": "Principal instalación naval colombiana en el Pacífico. Alberga la Escuela Naval y unidades de la Armada.",
        "functions": "Operaciones navales, formación y control marítimo.",
        "tags": ["infraestructura", "defensa", "naval"],
    },
    "CASA DE NARINO": {
        "description": "Residencia y despacho oficial del Presidente de la República. Sede de reuniones de alto nivel, consejos de ministros y recepción de jefes de Estado.",
        "functions": "Sede protocolaria y operativa de la Presidencia de la República.",
        "tags": ["gobierno", "ejecutivo", "presidencia"],
    },
    "PALACIO DE JUSTICIA": {
        "description": "Sede de la Corte Suprema de Justicia y del Consejo Superior de la Judicatura. Fue tomado por el M-19 en 1985, hecho que marcó la historia del país.",
        "functions": "Sede judicial y de gobierno de la rama judicial.",
        "tags": ["gobierno", "judicial", "memoria"],
    },
    "CENTRO DE MEMORIA HISTORICA": {
        "description": "Espacio de memoria y museo sobre el conflicto armado colombiano, ubicado en Bogotá.",
        "functions": "Memoria, educación y reparación simbólica.",
        "tags": ["gobierno", "memoria", "derechos humanos"],
    },
    "BIBLIOTECA NACIONAL DE COLOMBIA": {
        "description": "Depositaria del patrimonio bibliográfico y documental del país. Conserva archivos, libros y memoria impresa.",
        "functions": "Conservación, acceso y difusión del patrimonio bibliográfico.",
        "tags": ["gobierno", "cultura", "patrimonio"],
    },
    "MUSEO NACIONAL DE COLOMBIA": {
        "description": "Principal museo del país. Conserva y exhibe colecciones de historia, arte y arqueología.",
        "functions": "Conservación, investigación y exhibición.",
        "tags": ["gobierno", "cultura", "patrimonio"],
    },
}

TYPE_RULES = [
    (r"\bALCALDIA\b", "Alcaldía", "Ejecutivo territorial", "municipal"),
    (r"\bGOBERNACION\b", "Gobernación", "Ejecutivo territorial", "departamental"),
    (r"\bCONCEJO\b", "Concejo municipal", "Corporación territorial", "municipal"),
    (r"\bASAMBLEA\b", "Asamblea departamental", "Corporación territorial", "departamental"),
    (r"\bPERSONERIA\b", "Personería", "Ministerio Público", "municipal"),
    (r"\bCONTRALORIA\b", "Contraloría", "Control fiscal", "control"),
    (r"\bPROCURADURIA\b", "Procuraduría", "Ministerio Público", "control"),
    (r"\bDEFENSORIA\b", "Defensoría", "Ministerio Público", "control"),
    (r"\bFISCALIA\b", "Fiscalía", "Justicia", "judicial"),
    (r"\bCORTE\b", "Corte", "Alta corte", "judicial"),
    (r"\bCONSEJO DE ESTADO\b", "Consejo de Estado", "Alta corte", "judicial"),
    (r"\bCONSEJO SUPERIOR DE LA JUDICATURA\b", "Consejo Superior de la Judicatura", "Gobierno judicial", "judicial"),
    (r"\bJURISDICCION\b", "Jurisdicción", "Justicia", "judicial"),
    (r"\bMINISTERIO\b", "Ministerio", "Gobierno Nacional", "nacional"),
    (r"\bDEPARTAMENTO ADMINISTRATIVO\b", "Departamento Administrativo", "Gobierno Nacional", "nacional"),
    (r"\bSUPERINTENDENCIA\b", "Superintendencia", "Inspección y vigilancia", "nacional"),
    (r"\bUNIDAD ADMINISTRATIVA\b", "Unidad Administrativa Especial", "Gobierno Nacional", "nacional"),
    (r"\bAGENCIA\b", "Agencia", "Gobierno Nacional", "nacional"),
    (r"\bINSTITUTO\b", "Instituto", "Entidad pública", "nacional"),
    (r"\bCORPORACION AUTONOMA\b", "Corporación Autónoma Regional", "Autoridad ambiental", "regional"),
    (r"\bCORPORACION\b", "Corporación", "Entidad pública", "nacional"),
    (r"\bUNIVERSIDAD\b", "Universidad", "Educación superior", "nacional"),
    (r"\bESCUELA\b", "Escuela", "Educación", "nacional"),
    (r"\bHOSPITAL\b|\bE\.S\.E\.\b|\bESE\b", "Hospital / ESE", "Salud pública", "municipal"),
    (r"\bCAMARA DE COMERCIO\b", "Cámara de Comercio", "Gremio / registro", "municipal"),
    (r"\bNOTARIA\b", "Notaría", "Fe pública", "municipal"),
    (r"\bEMPRESA\b|\bE\.S\.P\.\b|\bE\.S\.E\.\b", "Empresa pública", "Servicios públicos", "municipal"),
    (r"\bFONDO\b", "Fondo", "Entidad pública", "nacional"),
    (r"\bCOMISION\b", "Comisión", "Entidad pública", "nacional"),
    (r"\bCONSEJO\b", "Consejo", "Entidad pública", "nacional"),
    (r"\bBANCO\b", "Banco público", "Finanzas públicas", "nacional"),
    (r"\bSENA\b", "Servicio Nacional de Aprendizaje", "Educación y empleo", "nacional"),
    (r"\bARCHIVO\b", "Archivo", "Cultura", "nacional"),
    (r"\bBIBLIOTECA\b", "Biblioteca", "Cultura", "nacional"),
    (r"\bMUSEO\b", "Museo", "Cultura", "nacional"),
]

SECTOR_POWER = {
    "Minas y Energía": 72,
    "Defensa": 70,
    "Hacienda y Crédito Público": 76,
    "Presidencia": 82,
    "Justicia y Derecho": 74,
    "Organismos de Control": 68,
    "Salud": 55,
    "Educación": 52,
    "Ambiente y Desarrollo Sostenible": 58,
    "Transporte": 60,
    "Agricultura y Desarrollo Rural": 52,
    "Tecnologías de la Información y Comunicaciones": 58,
    "Planeación": 54,
    "Inclusión Social y Reconciliación": 48,
    "Comercio, Industria y Turismo": 52,
    "Trabajo": 48,
    "Cultura": 42,
    "Deporte": 36,
    "Vivienda, Ciudad y Territorio": 50,
    "Estadísticas": 54,
}


def norm(value: object) -> str:
    text = str(value or "")
    replacements = {
        "Ãš": "U", "Ã“": "O", "Ã\x8d": "I", "Ã‘": "N", "Ã¡": "a", "Ã©": "e",
        "Ã³": "o", "Ãº": "u", "Ã±": "n", "Ã¼": "u", "Â": "", "â€“": "-",
        "â€”": "-", "â€™": "'", "â€œ": '"', "â€\x9d": '"',
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def clean_name(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def titlecase(value: str) -> str:
    value = clean_name(value)
    value = re.sub(r"\bD\.?\s*[Cc]\.?\b", "D.C.", value)
    value = re.sub(r",\s*D\.C\.", " D.C.", value)
    small = {"de", "del", "la", "las", "los", "y", "e", "en", "para", "por", "con", "al"}
    acronyms = {
        "S.A.S.", "S.A.", "LTDA.", "E.S.P.", "E.S.E.", "ESP", "ESE", "SAS", "SA",
        "LTDA", "CIA", "SCA", "BIC", "PYME", "XM", "USPEC", "URF", "DAPRE", "ANM",
        "ANH", "ANLA", "DIAN", "DANE", "APC", "ANT", "PGN", "FONPRECON", "UPRA",
        "IPSE", "SENA", "ICBF", "INCI", "INS", "IDEAM", "UPME", "CREG", "CRC",
        "CRA", "CNSC", "CNE", "JEP", "UBPD", "URT", "ART", "ADR", "ARN", "ANI",
        "DNP", "DAFP", "ESAP", "DANE", "DAPRE", "FNA", "FNG", "ICETEX", "RTVC",
        "SATENA", "INDUMIL", "FOGAFIN", "FOGACOOP", "FINAGRO", "BANCOLDEX",
        "FINDETER", "COLPENSIONES", "ADRES", "COLJUEGOS", "ITRC", "ALFM",
        "ANSV", "ANE", "ANIM", "APC", "AGN", "AUNAP", "ANTV", "CISA", "CNMH",
        "CGFM", "CRA", "CRC", "CREG", "CRIT", "CNSC", "CNO", "CONTE", "CPAE",
        "CPIP", "CPIQ", "COPNIA", "CPNT", "CTCP", "AND", "CCI", "AGROSAVIA",
        "CODALTEC", "COTECMAR", "CIAC", "CONIF", "PROPAIS", "DAPRE", "DANE",
    }
    whole_upper = value.isupper()
    words = []
    for i, word in enumerate(value.split()):
        up = word.upper()
        if up in acronyms:
            words.append(up)
        elif whole_upper and up in {"DE", "DEL", "LA", "LAS", "LOS", "Y", "E", "EN", "PARA", "POR", "CON", "AL"} and i > 0:
            words.append(word.lower())
        elif whole_upper:
            words.append(word.capitalize())
        elif word.isupper() and len(word) <= 6 and any(ch.isalpha() for ch in word):
            words.append(up)
        elif i > 0 and word.lower() in small:
            words.append(word.lower())
        elif word.isupper():
            words.append(word.capitalize())
        else:
            words.append(word)
    text = " ".join(words)
    text = re.sub(r"\bS A S\b", "S.A.S.", text)
    text = re.sub(r"\bS A\b", "S.A.", text)
    text = re.sub(r"\bLtda\b", "LTDA.", text)
    text = re.sub(r"\bD C\b", "D.C.", text)
    text = re.sub(r"\bD\.C\.\b", "D.C.", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_money(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text in {"-", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def point_ok(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and -4.6 <= lat <= 14.2 and -82.0 <= lon <= -66.0


def jitter_point(lat: float, lon: float, key: str, radius: float = 0.012) -> tuple[float, float]:
    """Desplaza ligeramente puntos geocodificados a municipio para que no se superpongan."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    angle = (int(digest[:8], 16) / 0xFFFFFFFF) * 6.283185307179586
    dist = (int(digest[8:16], 16) / 0xFFFFFFFF) ** 0.5 * radius
    return round(lat + dist * 0.85, 6), round(lon + dist, 6)


def fmt_int(value: object) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def load_divipola():
    rows = json.loads((RAW / "divipola.json").read_text())
    municipalities = {}
    by_name = defaultdict(list)
    dept_accum = defaultdict(list)
    dept_by_name = defaultdict(list)
    for row in rows:
        try:
            lat = float(str(row.get("latitud", "")).replace(",", "."))
            lon = float(str(row.get("longitud", "")).replace(",", "."))
        except ValueError:
            continue
        code = str(row.get("cod_mpio", "")).strip()
        name = clean_name(row.get("nom_mpio", ""))
        dept_code = str(row.get("cod_dpto", "")).strip()
        dept_name = clean_name(row.get("dpto", ""))
        item = {
            "code": code,
            "name": name,
            "dept_code": dept_code,
            "dept_name": dept_name,
            "lat": lat,
            "lon": lon,
        }
        municipalities[code] = item
        by_name[norm(name)].append(item)
        dept_by_name[norm(dept_name)].append(item)
        dept_accum[dept_code].append((lat, lon))
    dept_centroids = {}
    for code, points in dept_accum.items():
        dept_centroids[code] = (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )
    return municipalities, by_name, dept_centroids, dept_by_name


def match_city(city: str, dept: str, by_name, dept_by_name):
    key = norm(city)
    key = re.sub(r"\bD C\b", "", key).strip()
    key = key.replace("BOGOTA D C", "BOGOTA")
    aliases = {
        "CARTAGENA": "CARTAGENA DE INDIAS",
        "SAN ANDRES": "SAN ANDRES",
        "SAN JOSE DEL GUAVIARE": "SAN JOSE DEL GUAVIARE",
        "PUERTO CARREÑO": "PUERTO CARREÑO",
        "PUERTO CARRENO": "PUERTO CARREÑO",
        "MITU": "MITU",
        "INIRIDA": "INIRIDA",
        "GUAVIARE": "SAN JOSE DEL GUAVIARE",
        "SANTIAGO DE CALI": "CALI",
        "SAN JOSE DE CUCUTA": "CUCUTA",
        "SANTA FE DE BOGOTA": "BOGOTA",
        "SAN JUAN DE PASTO": "PASTO",
    }
    key = aliases.get(key, key)
    candidates = by_name.get(key, [])
    if candidates:
        return candidates[0]
    # Coincidencia por departamento si la ciudad no aparece.
    dept_candidates = dept_by_name.get(norm(dept), [])
    if dept_candidates:
        return dept_candidates[0]
    return None


def build_sigep():
    rows = json.loads((RAW / "sigep.json").read_text())
    lookup = {}
    for row in rows:
        key = norm(row.get("nombre_de_la_entidad"))
        employees = sum(
            fmt_int(row.get(k)) or 0
            for k in ("genero_hombre", "genero_mujer", "genero_no_binario")
        )
        if employees == 0:
            employees = sum(
                fmt_int(row.get(k)) or 0
                for k in ("edad_menor_o_igual_a_29", "edad_30_39", "edad_40_49", "edad_50_62", "edad_63_y_mas")
            )
        item = {
            "nit": str(row.get("nit", "")).strip(),
            "nature": row.get("naturaleza_jur_dica", ""),
            "sector": row.get("sector", ""),
            "employees": employees,
            "salary_avg": parse_money(row.get("salario_mensual_promedio")),
            "sigep_code": str(row.get("c_digo_sigep", "")).strip(),
            "raw_name": row.get("nombre_de_la_entidad", ""),
        }
        prev = lookup.get(key)
        if prev is None or (item["employees"] or 0) > (prev.get("employees") or 0):
            lookup[key] = item
    return lookup


def classify_public(name: str) -> tuple[str, str, str]:
    upper = norm(name)
    for pattern, subtype, branch, level in TYPE_RULES:
        if re.search(pattern, upper):
            return subtype, branch, level
    return "Entidad pública", "Sector público", "nacional"


def public_priority(subtype: str, level: str, coverage: str, employees: int) -> int:
    score = 30
    if level == "nacional":
        score = 100
    elif level == "departamental":
        score = 82
    elif subtype in {"Alcaldía"}:
        score = 72
    elif subtype in {"Hospital / ESE"}:
        score = 58
    elif subtype in {"Universidad", "Corporación Autónoma Regional", "Personería", "Concejo municipal"}:
        score = 52
    if coverage == "Nacional":
        score += 8
    if employees:
        score += min(18, int(employees ** 0.5 / 2))
    return score


def public_description(subtype: str, name: str, level: str, sector: str, municipality: str, department: str) -> str:
    place = municipality or department or "Colombia"
    sector_txt = sector if sector and sector != "NO APLICA" else "la administración pública"
    templates = {
        "Alcaldía": f"Alcaldía municipal de {place}. Ejecuta el presupuesto local, administra el suelo, presta servicios públicos y lidera la inversión en el municipio. Su capacidad de decisión depende de transferencias, regalías y contratación.",
        "Gobernación": f"Gobernación de {department or place}. Coordina el desarrollo departamental, ejecuta presupuesto y proyectos de infraestructura, salud, educación y seguridad.",
        "Concejo municipal": f"Corporación pública de representación municipal en {place}. Aprueba el plan de desarrollo, el presupuesto y los acuerdos; ejerce control político sobre la alcaldía.",
        "Asamblea departamental": f"Corporación pública de representación departamental. Aprueba ordenanzas, presupuesto y planes; ejerce control político sobre la gobernación.",
        "Personería": f"Ministerio Público en {place}. Vigila la conducta de servidores públicos, protege derechos humanos y atiende quejas ciudadanas.",
        "Hospital / ESE": f"Empresa Social del Estado en {place}. Presta servicios de salud en la red pública y depende de los flujos del sistema de salud y de la contratación territorial.",
        "Ministerio": f"Ministerio del Gobierno Nacional. Formula y ejecuta política pública en {sector_txt}; participa en el gabinete y en la agenda legislativa.",
        "Departamento Administrativo": f"Departamento Administrativo del Gobierno Nacional. Coordina política pública en {sector_txt} y articula entidades del sector.",
        "Superintendencia": f"Superintendencia del Estado. Ejerce inspección, vigilancia y control en {sector_txt}; puede sancionar y ordenar correctivos.",
        "Corte": f"Alta corte del poder judicial. Ejerce jurisdicción, unifica jurisprudencia y controla la legalidad o constitucionalidad de actos públicos.",
        "Fiscalía": f"Fiscalía General de la Nación. Dirige la investigación penal, formula acusaciones y articula la policía judicial.",
        "Contraloría": f"Órgano de control fiscal. Audita el manejo de recursos públicos y puede iniciar procesos de responsabilidad fiscal.",
        "Procuraduría": f"Ministerio Público. Vigila la conducta de servidores públicos y participa en procesos disciplinarios.",
        "Defensoría": f"Defensoría del Pueblo. Protege derechos humanos, atiende quejas y acompaña a víctimas.",
        "Corporación Autónoma Regional": f"Autoridad ambiental regional. Otorga permisos, licencias y administra los recursos naturales en su jurisdicción.",
        "Universidad": f"Institución de educación superior. Forma profesionales, produce investigación y participa en la vida pública de {place}.",
        "Cámara de Comercio": f"Cámara de Comercio de {place}. Administra el registro mercantil y representa los intereses del empresariado local.",
        "Notaría": f"Notaría pública en {place}. Ejerce fe pública y tramita actos notariales y registrales.",
        "Empresa pública": f"Empresa pública del sector {sector_txt}. Presta servicios o desarrolla actividades comerciales con participación estatal.",
        "Banco público": f"Banco con participación estatal. Financia sectores estratégicos y programas de política pública.",
    }
    if subtype in templates:
        return templates[subtype]
    return f"{subtype} del sector {sector_txt}, con cobertura {level} en {place}. Participa en la formulación, ejecución o control de políticas públicas. La ficha describe su mandato formal y no evalúa su desempeño."


def make_id(prefix: str, key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def main():
    municipalities, city_by_name, dept_centroids, dept_by_name = load_divipola()
    sigep = build_sigep()
    mintic = json.loads((RAW / "mintic.json").read_text())
    private_rows = json.loads((RAW / "supersociedades_2025.json").read_text())
    curated_path = CURATED / "curated_entities.json"
    curated_rows = json.loads(curated_path.read_text()) if curated_path.exists() else []

    # ---------- Entidades públicas ----------
    public = []
    for row in mintic:
        raw_name = clean_name(row.get("nombre_entidad"))
        if not raw_name:
            continue
        dept = clean_name(row.get("departamento"))
        mpio = clean_name(row.get("municipio"))
        mpio_code = str(row.get("divipola_municipio", "")).strip().zfill(5)
        dept_code = str(row.get("divipola_departamento", "")).strip().zfill(2)
        base_name = re.sub(r",\s*" + re.escape(dept) + r"\s*$", "", raw_name, flags=re.I) if dept else raw_name
        key = norm(base_name)
        info = sigep.get(key, {})
        subtype, branch, level_hint = classify_public(base_name)
        coverage = clean_name(row.get("cobertura_geogr_fica")) or "Nacional"
        level = "nacional" if coverage == "Nacional" or row.get("orden") == "Nacional" else (
            "departamental" if coverage == "Departamental" else "municipal"
        )
        if level_hint in {"judicial", "control"}:
            level = level_hint if level_hint == "judicial" else "nacional"
        sector = clean_name(row.get("sector")) or info.get("sector") or "Administración pública"
        employees = int(info.get("employees") or 0)
        mpio_item = municipalities.get(mpio_code, {})
        dept_name = mpio_item.get("dept_name") or dept
        municipality_name = mpio_item.get("name") or mpio
        lat = lon = None
        geo_precision = "municipio"
        geo = row.get("georreferenciaci_n_entidad") or {}
        if isinstance(geo, dict) and geo.get("type") == "Point" and len(geo.get("coordinates", [])) >= 2:
            lon, lat = float(geo["coordinates"][0]), float(geo["coordinates"][1])
        if not point_ok(lat, lon):
            try:
                lat = float(str(row.get("latitud_entidad", "")).replace(",", "."))
                lon = float(str(row.get("longitud_entidad", "")).replace(",", "."))
            except ValueError:
                lat = lon = None
        if point_ok(lat, lon):
            geo_precision = "entidad"
        else:
            if mpio_item:
                lat, lon = mpio_item["lat"], mpio_item["lon"]
            else:
                lat, lon = dept_centroids.get(dept_code, (4.0, -73.0))
            geo_precision = "municipio"
        priority = public_priority(subtype, level, coverage, employees)
        sector_power = SECTOR_POWER.get(sector, 45)
        political = min(98, 30 + (30 if level == "nacional" else 20 if level == "departamental" else 8) + (12 if subtype in {"Corte", "Fiscalía", "Contraloría", "Procuraduría"} else 0) + min(12, employees // 250))
        geographic = min(96, 35 + (45 if level == "nacional" else 28 if level == "departamental" else 10) + (8 if coverage == "Nacional" else 0))
        economic = min(92, sector_power + min(14, employees // 300))
        known = KNOWN.get(key) or KNOWN.get(norm(raw_name))
        display_municipality = titlecase(municipality_name) if municipality_name else ""
        display_department = titlecase(dept_name) if dept_name else ""
        description = known.get("description") if known else public_description(subtype, base_name, level, sector, display_municipality, display_department)
        functions = known.get("functions") if known else public_description(subtype, base_name, level, sector, display_municipality, display_department)
        power_note = known.get("power_note") if known else "Perfil preliminar construido con nivel administrativo, cobertura y número de empleados. No mide captura, corrupción ni influencia informal."
        tags = list(dict.fromkeys([subtype.lower(), level, sector.lower()] + (known.get("tags", []) if known else [])))
        entity = {
            "id": make_id("pub", f"{key}|{mpio_code}"),
            "name": titlecase(base_name),
            "family": "public",
            "subtype": subtype,
            "branch": branch,
            "level": level,
            "coverage": coverage,
            "sector": sector,
            "department": titlecase(dept_name) if dept_name else "",
            "municipality": titlecase(municipality_name) if municipality_name else "",
            "department_code": dept_code,
            "municipality_code": mpio_code,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "geo_precision": geo_precision,
            "description": description,
            "functions": functions,
            "relevance": max(20, min(100, priority + (10 if known else 0))),
            "power": {
                "political": political,
                "geographic": geographic,
                "economic": economic,
                "extractive": 0,
            },
            "power_note": power_note,
            "metrics": {
                "employees": employees or None,
                "salary_avg": info.get("salary_avg"),
                "nit": info.get("nit") or None,
                "sigep_code": info.get("sigep_code") or None,
            },
            "ownership": "Estado",
            "tags": tags,
            "sources": [SOURCE_MINTIC, SOURCE_SIGEP, SOURCE_DIVIPOLA],
            "confidence": "A" if geo_precision == "entidad" else "B",
            "updated": TODAY,
        }
        public.append(entity)

    # Deduplicar por id y ordenar por prioridad.
    dedup = {}
    for entity in public:
        dedup[entity["id"]] = entity
    public = sorted(
        dedup.values(),
        key=lambda e: (e["relevance"], e["metrics"].get("employees") or 0, e["name"]),
        reverse=True,
    )[:PUBLIC_TARGET]
    public_ids = {e["id"] for e in public}
    public_names = {norm(e["name"]) for e in public}

    # ---------- Empresas privadas ----------
    private = []
    for row in private_rows:
        name = clean_name(row.get("raz_n_social"))
        if not name:
            continue
        key = norm(name)
        # Evitar duplicar entidades que ya vienen del directorio público.
        if key in public_names:
            continue
        revenue = parse_money(row.get("ingresos_operacionales"))
        assets = parse_money(row.get("total_activos"))
        profit = parse_money(row.get("ganancia_p_rdida"))
        nit = str(row.get("nit", "")).strip()
        city = clean_name(row.get("ciudad_domicilio"))
        dept = clean_name(row.get("departamento_domicilio"))
        city_item = match_city(city, dept, city_by_name, dept_by_name)
        if city_item:
            lat, lon = city_item["lat"], city_item["lon"]
            municipality_name = city_item["name"]
            dept_name = city_item["dept_name"]
            geo_precision = "municipio"
        else:
            lat, lon = 4.0, -73.0
            municipality_name = city or ""
            dept_name = dept
            geo_precision = "departamento"
        known = KNOWN.get(key)
        is_state = key in STATE_COMPANIES or any(token in key for token in STATE_COMPANIES if len(token) > 5)
        family = "state_company" if is_state else "private"
        macrosector = clean_name(row.get("macrosector")) or "Empresas"
        ciiu = str(row.get("ciiu", "")).strip()
        economic = 40 + min(60, int((revenue or 0) ** 0.5))
        description = known.get("description") if known else (
            f"Empresa del sector {macrosector.lower()} con ingresos operacionales reportados por "
            f"{revenue:.2f} billones de COP en el corte 2025. CIIU {ciiu or 'sin dato'}. "
            f"Su ficha describe actividad y tamaño; no implica una evaluación de conducta."
        ) if revenue is not None else (
            f"Empresa del sector {macrosector.lower()} reportada por Supersociedades. CIIU {ciiu or 'sin dato'}."
        )
        entity = {
            "id": make_id("pri", nit or key),
            "name": titlecase(name),
            "family": family,
            "subtype": "Empresa estatal" if is_state else "Empresa privada",
            "branch": "Privado" if not is_state else "Estatal / mixto",
            "level": "nacional" if (revenue or 0) >= 1 else "regional",
            "coverage": "Nacional",
            "sector": titlecase(macrosector),
            "department": titlecase(dept_name) if dept_name else "",
            "municipality": titlecase(municipality_name) if municipality_name else "",
            "department_code": "",
            "municipality_code": city_item["code"] if city_item else "",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "geo_precision": geo_precision,
            "description": description,
            "functions": known.get("functions") if known else f"Actividad económica principal: {macrosector.lower()} (CIIU {ciiu or 'sin dato'}).",
            "relevance": max(22, min(100, 35 + int((revenue or 0) ** 0.5))),
            "power": {
                "political": 0,
                "geographic": 55 if (revenue or 0) >= 5 else 38,
                "economic": max(20, min(100, economic)),
                "extractive": 78 if macrosector.upper() in {"MINERO", "PETROLEO", "ENERGIA", "MINAS"} else 0,
            },
            "power_note": known.get("power_note") if known else "Perfil preliminar basado en ingresos, activos y sector. No incluye contratación pública, financiamiento de campañas ni relaciones societarias no verificadas.",
            "metrics": {
                "revenue_billions": revenue,
                "assets_billions": assets,
                "profit_billions": profit,
                "year": 2025,
                "nit": nit or None,
                "ciiu": ciiu or None,
            },
            "ownership": known.get("ownership") if known else ("Estado / mixta" if is_state else "Privada"),
            "tags": list(dict.fromkeys(["empresa", macrosector.lower(), "privada" if not is_state else "estatal"] + (known.get("tags", []) if known else []))),
            "sources": [SOURCE_SUPERSOC, SOURCE_DIVIPOLA],
            "confidence": "B" if not known else "A",
            "updated": TODAY,
        }
        private.append(entity)
    private.sort(key=lambda e: (e["metrics"].get("revenue_billions") or 0, e["metrics"].get("assets_billions") or 0), reverse=True)
    private_all = private
    private = private_all[:PRIVATE_TARGET]
    existing_names = {norm(e["name"]) for e in public + private}

    # ---------- Curaduría propia ----------
    curated = []
    for row in curated_rows:
        name = clean_name(row.get("name"))
        if not name:
            continue
        key = norm(name)
        if row.get("merge_only"):
            continue
        if key in existing_names:
            continue
        city = clean_name(row.get("city") or row.get("municipality") or "Bogotá D.C.")
        city_item = match_city(city, row.get("department", ""), city_by_name, dept_by_name)
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            if city_item:
                lat, lon = city_item["lat"], city_item["lon"]
            else:
                lat, lon = 4.65, -74.08
            geo_precision = "municipio"
        else:
            geo_precision = row.get("geo_precision", "aproximada")
        family = row.get("family", "civil")
        subtype = row.get("subtype", "Actor estratégico")
        sector = row.get("sector", "Sociedad civil")
        level = row.get("level", "nacional")
        relevance = int(row.get("relevance", 65))
        power = row.get("power", {})
        entity = {
            "id": make_id("cur", key),
            "name": name,
            "family": family,
            "subtype": subtype,
            "branch": row.get("branch", "No estatal" if family in {"civil", "private", "international"} else "Estatal"),
            "level": level,
            "coverage": row.get("coverage", "Nacional"),
            "sector": sector,
            "department": titlecase(row.get("department") or (city_item["dept_name"] if city_item else "Bogotá D.C.")),
            "municipality": titlecase(row.get("municipality") or city),
            "department_code": city_item["dept_code"] if city_item else "",
            "municipality_code": city_item["code"] if city_item else "",
            "lat": round(float(lat), 6),
            "lon": round(float(lon), 6),
            "geo_precision": geo_precision,
            "description": row.get("description", "Actor estratégico del ecosistema político, económico o social colombiano."),
            "functions": row.get("functions", "Incidencia, representación o coordinación."),
            "relevance": relevance,
            "power": {
                "political": int(power.get("political", 50)),
                "geographic": int(power.get("geographic", 45)),
                "economic": int(power.get("economic", 45)),
                "extractive": int(power.get("extractive", 0)),
            },
            "power_note": row.get("power_note", "Perfil preliminar; no constituye una acusación ni una medición oficial de poder."),
            "metrics": row.get("metrics", {}),
            "ownership": row.get("ownership", "No estatal" if family in {"civil", "private", "international"} else "Estado"),
            "tags": list(dict.fromkeys(row.get("tags", [subtype.lower(), family]))),
            "sources": row.get("sources", [{"name": "Curaduría SARCOL MAP", "url": "", "date": TODAY, "license": "CC BY-SA 4.0"}]),
            "confidence": row.get("confidence", "C"),
            "updated": TODAY,
        }
        curated.append(entity)
        existing_names.add(key)

    # ---------- Ensamblado exacto ----------
    entities = public + private + curated
    if len(entities) > TOTAL_TARGET:
        # Recortar primero curaduría de menor relevancia y luego empresas.
        curated_sorted = sorted(curated, key=lambda e: e["relevance"], reverse=True)
        keep_curated = curated_sorted[: max(0, TOTAL_TARGET - len(public) - len(private))]
        keep_private = private[: max(0, TOTAL_TARGET - len(public) - len(keep_curated))]
        entities = public + keep_private + keep_curated
    if len(entities) < TOTAL_TARGET:
        # Completar con más empresas del ranking completo.
        used = {e["id"] for e in entities}
        for entity in private_all:
            if entity["id"] not in used:
                entities.append(entity)
                used.add(entity["id"])
            if len(entities) >= TOTAL_TARGET:
                break
    entities = entities[:TOTAL_TARGET]
    entities.sort(key=lambda e: (e["relevance"], e["name"]), reverse=True)

    # Separar visualmente los puntos que solo tienen geocodificación municipal.
    for e in entities:
        if e["geo_precision"] == "municipio":
            e["lat"], e["lon"] = jitter_point(e["lat"], e["lon"], e["id"], 0.012)
            e["geo_note"] = "Ubicación aproximada al municipio; el punto se desplaza ligeramente para evitar superposición."
        elif e["geo_precision"] == "departamento":
            e["lat"], e["lon"] = jitter_point(e["lat"], e["lon"], e["id"], 0.035)
            e["geo_note"] = "Ubicación aproximada al departamento; el punto se desplaza ligeramente para evitar superposición."
        elif e["geo_precision"] == "aproximada":
            e["geo_note"] = "Ubicación aproximada de la sede principal. No debe usarse para análisis predial."

    # ---------- Salidas ----------
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "entities.json").write_text(json.dumps(entities, ensure_ascii=False, separators=(",", ":")))
    features = []
    for e in entities:
        features.append({
            "type": "Feature",
            "id": e["id"],
            "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
            "properties": {
                "id": e["id"],
                "name": e["name"],
                "family": e["family"],
                "subtype": e["subtype"],
                "level": e["level"],
                "sector": e["sector"],
                "department": e["department"],
                "municipality": e["municipality"],
                "relevance": e["relevance"],
                "confidence": e["confidence"],
                "ownership": e["ownership"],
                "revenue": e["metrics"].get("revenue_billions") or 0,
                "employees": e["metrics"].get("employees") or 0,
            },
        })
    (OUT / "entities-map.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, separators=(",", ":")))

    stats = {
        "total": len(entities),
        "by_family": dict(Counter(e["family"] for e in entities)),
        "by_level": dict(Counter(e["level"] for e in entities)),
        "by_sector": dict(Counter(e["sector"] for e in entities).most_common(25)),
        "by_department": dict(Counter(e["department"] for e in entities if e["department"]).most_common(40)),
        "by_confidence": dict(Counter(e["confidence"] for e in entities)),
        "sources": [SOURCE_MINTIC, SOURCE_SIGEP, SOURCE_SUPERSOC, SOURCE_DIVIPOLA],
        "updated": TODAY,
        "note": "Selección curada de 5.000 registros. No es un censo exhaustivo de todas las entidades del Estado ni de todas las empresas.",
    }
    (OUT / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    print("Entidades:", len(entities), dict(Counter(e["family"] for e in entities)))
    print("Fuentes:", stats["by_confidence"])
    print("Salida:", OUT / "entities.json", (OUT / "entities.json").stat().st_size / 1e6, "MB")
    print("Mapa:", (OUT / "entities-map.geojson").stat().st_size / 1e6, "MB")


if __name__ == "__main__":
    main()
