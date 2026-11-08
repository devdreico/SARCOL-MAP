import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUpRight, Layers3, LoaderCircle, MapPin, Search, X } from 'lucide-react'
import type { GeoJSONSource, Map as MapLibreMap, MapLayerMouseEvent } from 'maplibre-gl'
import type { FeatureCollection, Point } from 'geojson'
import '@fontsource-variable/montserrat'
import 'maplibre-gl/dist/maplibre-gl.css'
import './App.css'

type Family = 'public' | 'private' | 'civil' | 'infrastructure' | 'international' | 'state_company'
type FamilyFilter = 'all' | Family

type Entity = {
  id: string
  name: string
  family: Family
  subtype: string
  level: string
  coverage: string
  sector: string
  department: string
  municipality: string
  lat: number
  lon: number
  description: string
  functions: string
  relevance: number
  confidence: 'A' | 'B' | 'C'
  sources: { name: string; url: string; date: string; license: string }[]
}

const familyLabels: Record<Family, string> = {
  public: 'Público',
  private: 'Privado',
  civil: 'Sociedad civil',
  infrastructure: 'Infraestructura',
  international: 'Internacional',
  state_company: 'Empresa estatal',
}

const familyColors: Record<Family, string> = {
  public: '#167c70',
  private: '#d46b45',
  civil: '#b57a23',
  infrastructure: '#487ca4',
  international: '#7169a4',
  state_company: '#3e648e',
}

const numberFormat = new Intl.NumberFormat('es-CO')

function toFeatureCollection(items: Entity[]): FeatureCollection<Point, Entity> {
  return {
    type: 'FeatureCollection',
    features: items
      .filter((entity) => Number.isFinite(entity.lat) && Number.isFinite(entity.lon))
      .map((entity) => ({
        type: 'Feature',
        id: entity.id,
        geometry: { type: 'Point', coordinates: [entity.lon, entity.lat] },
        properties: entity,
      })),
  }
}

function App() {
  const [entities, setEntities] = useState<Entity[]>([])
  const [query, setQuery] = useState('')
  const [family, setFamily] = useState<FamilyFilter>('all')
  const [department, setDepartment] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [mapReady, setMapReady] = useState(false)
  const [mapError, setMapError] = useState(false)
  const deferredQuery = useDeferredValue(query)
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    fetch('/data/entities.json', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('No fue posible cargar el atlas de entidades.')
        return response.json() as Promise<Entity[]>
      })
      .then((data) => {
        setEntities(data)
        setLoading(false)
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setLoadError(error instanceof Error ? error.message : 'Error al cargar los datos.')
        setLoading(false)
      })

    return () => controller.abort()
  }, [])

  const departments = useMemo(
    () => [...new Set(entities.map((entity) => entity.department).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es')),
    [entities],
  )

  const filteredEntities = useMemo(() => {
    const normalizedQuery = deferredQuery.trim().toLocaleLowerCase('es-CO')

    return entities.filter((entity) => {
      if (family !== 'all' && entity.family !== family) return false
      if (department && entity.department !== department) return false
      if (!normalizedQuery) return true

      return [entity.name, entity.municipality, entity.department, entity.sector, entity.subtype]
        .join(' ')
        .toLocaleLowerCase('es-CO')
        .includes(normalizedQuery)
    })
  }, [department, deferredQuery, entities, family])

  const selectedEntity = filteredEntities.find((entity) => entity.id === selectedId) ?? null

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return
    let disposed = false

    const initializeMap = async () => {
      const { AttributionControl, Map: MapConstructor, NavigationControl } = await import('maplibre-gl')
      if (disposed || !mapContainer.current) return

      const map = new MapConstructor({
        container: mapContainer.current,
        style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
        center: [-73.4, 4.4],
        zoom: 4.25,
        minZoom: 3,
        maxZoom: 15,
        attributionControl: false,
      })

      mapRef.current = map
      map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
      map.addControl(new AttributionControl({ compact: true }), 'bottom-left')

      map.on('error', () => {
        if (!map.isStyleLoaded()) setMapError(true)
      })

      map.on('load', () => {
        map.addSource('entities', {
          type: 'geojson',
          data: toFeatureCollection([]),
          cluster: true,
          clusterMaxZoom: 9,
          clusterRadius: 42,
        })

        map.addLayer({
          id: 'entity-clusters',
          type: 'circle',
          source: 'entities',
          filter: ['has', 'point_count'],
          paint: {
            'circle-color': '#173f43',
            'circle-radius': ['step', ['get', 'point_count'], 17, 25, 21, 100, 26, 500, 32],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 2,
          },
        })
        map.addLayer({
          id: 'cluster-count',
          type: 'symbol',
          source: 'entities',
          filter: ['has', 'point_count'],
          layout: { 'text-field': '{point_count_abbreviated}', 'text-font': ['Open Sans Bold'], 'text-size': 11 },
          paint: { 'text-color': '#ffffff' },
        })
        map.addLayer({
          id: 'entity-points',
          type: 'circle',
          source: 'entities',
          filter: ['!', ['has', 'point_count']],
          paint: {
            'circle-color': [
              'match', ['get', 'family'],
              'public', familyColors.public,
              'private', familyColors.private,
              'civil', familyColors.civil,
              'infrastructure', familyColors.infrastructure,
              'international', familyColors.international,
              'state_company', familyColors.state_company,
              '#737c77',
            ],
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 3.5, 8, 6, 12, 9],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1.25,
            'circle-opacity': 0.88,
          },
        })

        map.on('click', 'entity-clusters', (event: MapLayerMouseEvent) => {
          const cluster = map.queryRenderedFeatures(event.point, { layers: ['entity-clusters'] })[0]
          const clusterId = cluster?.properties?.cluster_id
          const source = map.getSource('entities') as GeoJSONSource
          if (typeof clusterId !== 'number') return

          source.getClusterExpansionZoom(clusterId).then((zoom) => {
            const coordinates = (cluster.geometry as Point).coordinates as [number, number]
            map.easeTo({ center: coordinates, zoom, duration: 450 })
          })
        })
        map.on('click', 'entity-points', (event: MapLayerMouseEvent) => {
          const id = event.features?.[0]?.properties?.id
          if (typeof id === 'string') setSelectedId(id)
        })
        map.on('mouseenter', 'entity-clusters', () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', 'entity-clusters', () => { map.getCanvas().style.cursor = '' })
        map.on('mouseenter', 'entity-points', () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', 'entity-points', () => { map.getCanvas().style.cursor = '' })
        setMapError(false)
        setMapReady(true)
      })
    }

    void initializeMap().catch(() => {
      if (!disposed) setMapError(true)
    })

    return () => {
      disposed = true
      mapRef.current?.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const source = mapRef.current?.getSource('entities') as GeoJSONSource | undefined
    if (mapReady && source) source.setData(toFeatureCollection(filteredEntities))
  }, [filteredEntities, mapReady])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return

    map.setPaintProperty('entity-points', 'circle-stroke-color', [
      'case', ['==', ['get', 'id'], selectedId ?? ''], '#f05b3f', '#ffffff',
    ])
    if (selectedEntity) {
      map.flyTo({ center: [selectedEntity.lon, selectedEntity.lat], zoom: Math.max(map.getZoom(), 7), duration: 700 })
    }
  }, [mapReady, selectedEntity, selectedId])

  const visibleEntities = filteredEntities.slice(0, 100)

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="SARCOL MAP, inicio">
          <span className="brand-mark"><MapPin size={18} strokeWidth={2.2} /></span>
          <span className="brand-name">SARCOL<span>MAP</span></span>
        </a>
        <div className="topbar-meta"><span className="live-dot" /> ATLAS DE PODER COLOMBIANO <span className="topbar-separator">/</span> DATOS ABIERTOS</div>
        <a className="about-link" href="https://github.com/devdreico/SARCOL-MAP" target="_blank" rel="noreferrer">
          Proyecto <ArrowUpRight size={14} />
        </a>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          <div className="sidebar-heading">
            <p className="eyebrow">COLOMBIA · 2026</p>
            <h1>El poder,<br /><em>en el mapa.</em></h1>
            <p className="intro">Instituciones, empresas y organizaciones que mueven el país. Un atlas para explorar quiénes son y dónde están.</p>
          </div>

          <div className="search-box">
            <Search size={17} aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar entidad, sector, ciudad..."
              aria-label="Buscar entidades"
            />
            {query && <button className="clear-search" type="button" onClick={() => setQuery('')} aria-label="Limpiar búsqueda"><X size={15} /></button>}
            {!query && <kbd>⌘ K</kbd>}
          </div>

          <div className="filters">
            <div className="filter-label"><span>Explorar por tipo</span><Layers3 size={14} /></div>
            <div className="family-filters" role="group" aria-label="Filtrar por tipo de entidad">
              {(['all', 'public', 'private', 'civil', 'infrastructure', 'international', 'state_company'] as FamilyFilter[]).map((value) => (
                <button key={value} type="button" className={family === value ? 'filter-chip active' : 'filter-chip'} onClick={() => setFamily(value)}>
                  {value === 'all' ? 'Todas' : familyLabels[value]}
                </button>
              ))}
            </div>
            <label className="department-select">
              <span>Departamento</span>
              <select value={department} onChange={(event) => setDepartment(event.target.value)}>
                <option value="">Todo el país</option>
                {departments.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </label>
          </div>

          <div className="results-heading">
            <div><span className="eyebrow">RESULTADOS</span><strong>{loading ? '...' : numberFormat.format(filteredEntities.length)}</strong></div>
            <span className="results-caption">de {numberFormat.format(entities.length)} fichas</span>
          </div>

          <section className="entity-list" aria-label="Entidades">
            {loading && <div className="loading-state"><LoaderCircle size={17} className="spin" /> Cargando entidades</div>}
            {loadError && <p className="error-state">{loadError}</p>}
            {!loading && !loadError && filteredEntities.length === 0 && <p className="empty-state">No encontramos coincidencias. Prueba con otro término o filtro.</p>}
            {visibleEntities.map((entity) => (
              <button
                className={selectedId === entity.id ? 'entity-row selected' : 'entity-row'}
                key={entity.id}
                type="button"
                onClick={() => setSelectedId(entity.id)}
              >
                <span className="entity-color" style={{ backgroundColor: familyColors[entity.family] ?? '#737c77' }} />
                <span className="entity-copy">
                  <strong>{entity.name}</strong>
                  <span>{entity.municipality || entity.department} <i>·</i> {entity.sector || familyLabels[entity.family]}</span>
                </span>
                <ArrowUpRight className="row-arrow" size={15} />
              </button>
            ))}
            {!loading && filteredEntities.length > visibleEntities.length && (
              <p className="list-limit">Mostrando las primeras {numberFormat.format(visibleEntities.length)}. Afina la búsqueda para encontrar una entidad.</p>
            )}
          </section>

          <footer className="sidebar-footer">
            <span><i className="confidence-dot" /> Datos con fuentes públicas</span>
            <span>Actualizado · 27 OCT 2026</span>
          </footer>
        </aside>

        <section className="map-panel" aria-label="Mapa de entidades">
          <div className="map-heading">
            <div><span className="eyebrow">VISTA TERRITORIAL</span><h2>Colombia</h2></div>
            <div className="map-legend" aria-label="Leyenda del mapa">
              <span><i style={{ background: familyColors.public }} /> Público</span>
              <span><i style={{ background: familyColors.private }} /> Privado</span>
              <span><i style={{ background: familyColors.civil }} /> Sociedad civil</span>
            </div>
          </div>
          <div className="map-frame">
            <div ref={mapContainer} className="map-canvas" />
            {!mapReady && !mapError && <div className="map-loading"><LoaderCircle size={18} className="spin" /> Preparando mapa</div>}
            {mapError && <div className="map-fallback"><MapPin size={19} /><span>El mapa base no está disponible. La búsqueda y las fichas siguen activas.</span></div>}
            <div className="map-stamp"><span className="live-dot" /> {numberFormat.format(filteredEntities.length)} PUNTOS VISIBLES</div>
            {selectedEntity && (
              <div className="map-selection">
                <button type="button" className="selection-close" onClick={() => setSelectedId(null)} aria-label="Cerrar ficha"><X size={15} /></button>
                <span className="eyebrow">{familyLabels[selectedEntity.family] ?? selectedEntity.subtype}</span>
                <strong>{selectedEntity.name}</strong>
                <span>{selectedEntity.municipality}, {selectedEntity.department}</span>
                <p>{selectedEntity.description}</p>
                {selectedEntity.sources[0] && <a href={selectedEntity.sources[0].url} target="_blank" rel="noreferrer">Fuente: {selectedEntity.sources[0].name} <ArrowUpRight size={12} /></a>}
              </div>
            )}
          </div>
          <div className="map-caption"><span>Haz clic en un punto o grupo para acercarte.</span><span>Fuentes: MinTIC · SIGEP · DANE · Supersociedades</span></div>
        </section>
      </div>
    </main>
  )
}

export default App
