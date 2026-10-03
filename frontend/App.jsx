import { useState, useEffect, useCallback } from 'react'

async function api(path, method = 'GET', body) {
  const token = localStorage.getItem('token')
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token && { Authorization: `Bearer ${token}` }) },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (res.status === 401) { localStorage.clear(); window.location.reload() }
  if (!res.ok) {
    const d = data.detail
    if (Array.isArray(d)) throw new Error(d.map(x => `${x.loc.slice(-1)}: ${x.msg}`).join('; '))
    throw new Error(typeof d === 'string' ? d : d?.message || 'Request failed')
  }
  return data
}

const F = ({ label, ...p }) => <label className="f">{label}<input {...p} /></label>

function Login({ onLogin }) {
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState('')
  const submit = async e => {
    e.preventDefault()
    setErr('')
    const res = await fetch('/api/auth/login', { method: 'POST', body: new URLSearchParams({ username: u, password: p }) })
    const d = await res.json().catch(() => ({}))
    if (!res.ok) return setErr(d.detail || 'Login failed')
    localStorage.setItem('token', d.access_token)
    onLogin(d.user)
  }
  return (
    <form className="card login" onSubmit={submit}>
      <h2>IP Inventory</h2>
      <F label="Username" value={u} onChange={e => setU(e.target.value)} autoFocus />
      <F label="Password" type="password" value={p} onChange={e => setP(e.target.value)} />
      {err && <div className="err">{err}</div>}
      <button type="submit">Login</button>
    </form>
  )
}

function Assign({ row, onSave, onClose }) {
  const [d, setD] = useState({ room: '', equipment_id: '', equipment_name: '', cpu_serial: '', instrument_serial: '', user_name: '', remarks: '' })
  return (
    <div className="modal"><div className="card">
      <h3>Assign {row.ip}</h3>
      <p className="muted">VLAN {row.vlan_id} · {row.location}{row.department && ` · ${row.department}`}</p>
      {Object.keys(d).map(k => <F key={k} label={k.replace('_', ' ')} value={d[k]} onChange={e => setD({ ...d, [k]: e.target.value })} />)}
      <div className="row">
        <button onClick={() => onSave(Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v.trim() || null])))}>Assign</button>
        <button className="ghost" onClick={onClose}>Cancel</button>
      </div>
    </div></div>
  )
}

function IpPage() {
  const [vlans, setVlans] = useState([])
  const [f, setF] = useState({ vlan_pk: '', status: '', q: '' })
  const [data, setData] = useState({ items: [], total: 0 })
  const [page, setPage] = useState(1)
  const [sel, setSel] = useState(null)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const p = new URLSearchParams({ page, page_size: 25 })
    Object.entries(f).forEach(([k, v]) => v && p.set(k, v))
    try { setData(await api(`/api/ips?${p}`)) } catch (e) { setMsg(e.message) }
  }, [f, page])
  useEffect(() => { load() }, [load])
  useEffect(() => { api('/api/ips/vlans').then(setVlans).catch(() => {}) }, [])

  const act = async (path, body) => {
    try { await api(path, 'POST', body); setMsg(''); setSel(null) } catch (e) { setMsg(e.message) }
    load()
  }
  const flt = k => e => { setPage(1); setF({ ...f, [k]: e.target.value }) }
  const st = (r, status) => act(`/api/ips/${r.id}/status`, { status })

  return (
    <>
      <div className="bar">
        <select value={f.vlan_pk} onChange={flt('vlan_pk')}>
          <option value="">All VLANs</option>
          {vlans.map(v => <option key={v.id} value={v.id}>VLAN {v.vlan_id} - {v.name} ({v.available} free)</option>)}
        </select>
        <select value={f.status} onChange={flt('status')}>
          <option value="">All statuses</option>
          {['available', 'assigned', 'reserved', 'inactive'].map(s => <option key={s}>{s}</option>)}
        </select>
        <input placeholder="Search IP, equipment, user, serial" value={f.q} onChange={flt('q')} style={{ width: 280 }} />
      </div>
      {msg && <div className="err">{msg}</div>}
      <table>
        <thead><tr>{['IP', 'VLAN', 'Status', 'Equipment', 'User', 'Room', ''].map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{data.items.map(r => (
          <tr key={r.id}>
            <td>{r.ip}</td><td>{r.vlan_id}</td>
            <td><span className={`tag ${r.status}`}>{r.status}{r.reserved_reason ? ` (${r.reserved_reason})` : ''}</span></td>
            <td>{r.equipment_name}<br /><small className="muted">{r.equipment_id}</small></td>
            <td>{r.user_name}</td><td>{r.room}</td>
            <td className="acts">
              {r.status === 'available' && <button onClick={() => setSel(r)}>Assign</button>}
              {r.status === 'assigned' && <button className="ghost" onClick={() => st(r, 'inactive')}>Set inactive</button>}
              {r.status === 'inactive' && <button className="ghost" onClick={() => st(r, 'assigned')}>Reactivate</button>}
              {['assigned', 'inactive'].includes(r.status) &&
                <button className="danger" onClick={() => window.confirm(`Release ${r.ip}?`) && act(`/api/ips/${r.id}/release`)}>Release</button>}
            </td>
          </tr>
        ))}</tbody>
      </table>
      <div className="row">
        <button className="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
        <span>Page {page} · {data.total} IPs</span>
        <button className="ghost" disabled={page * 25 >= data.total} onClick={() => setPage(page + 1)}>Next</button>
      </div>
      {sel && <Assign row={sel} onClose={() => setSel(null)} onSave={d => act(`/api/ips/${sel.id}/assign`, d)} />}
    </>
  )
}

function VlanPage() {
  const [list, setList] = useState([])
  const [d, setD] = useState({ vlan_id: '', name: '', network_address: '', cidr: '24', gateway: '', primary_dns: '', location: '', department: '', reserved_ips: '' })
  const [prev, setPrev] = useState(null)
  const [msg, setMsg] = useState({ text: '', ok: false })
  const load = () => api('/api/vlans').then(setList).catch(e => setMsg({ text: e.message }))
  useEffect(() => { load() }, [])

  const body = () => ({
    ...d, vlan_id: +d.vlan_id, cidr: +d.cidr, primary_dns: d.primary_dns || null, department: d.department || null,
    reserved_ips: d.reserved_ips.split(',').map(s => s.trim()).filter(Boolean),
  })
  const preview = async () => {
    try { setMsg({ text: '' }); setPrev(await api('/api/vlans/preview', 'POST', body())) }
    catch (e) { setPrev(null); setMsg({ text: e.message }) }
  }
  const create = async () => {
    try { const r = await api('/api/vlans', 'POST', body()); setMsg({ text: r.message, ok: true }); setPrev(null); load() }
    catch (e) { setMsg({ text: e.message }) }
  }
  const s = prev?.summary

  return (
    <>
      <div className="card">
        <h3>Create VLAN</h3>
        <div className="grid">
          {Object.keys(d).map(k => <F key={k} label={k.replace('_', ' ')} value={d[k]} onChange={e => setD({ ...d, [k]: e.target.value })} />)}
        </div>
        <small className="muted">Reserved IPs: comma separated, e.g. 10.10.20.10, 10.10.20.11 (the gateway is reserved automatically)</small>
        <div className="row"><button onClick={preview}>Preview</button></div>
        {msg.text && <div className={msg.ok ? 'ok' : 'err'}>{msg.text}</div>}
        {prev && (
          <div>
            <p><b>{s.network}</b> · mask {s.subnet_mask} · {s.usable_ips} usable IPs ({s.available_count} available, {s.reserved_count} reserved)</p>
            {prev.conflicts.map(c => <div key={c.vlan_id} className="err">Overlaps VLAN {c.vlan_id} - {c.name} ({c.network}/{c.cidr})</div>)}
            {prev.vlan_id_taken && <div className="err">This VLAN ID already exists.</div>}
            <small className="muted">First: {prev.rows.head.slice(0, 3).map(r => r.ip).join(', ')} … Last: {prev.rows.tail.slice(-1)[0]?.ip}</small>
            <div className="row"><button disabled={!prev.can_create} onClick={create}>Confirm &amp; Generate IPs</button></div>
          </div>
        )}
      </div>
      <table>
        <thead><tr>{['VLAN', 'Name', 'Network', 'Location', 'Dept', 'Total', 'Assigned', 'Available', 'Reserved', 'Used %'].map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{list.map(v => (
          <tr key={v.id}><td>{v.vlan_id}</td><td>{v.name}</td><td>{v.network}/{v.cidr}</td><td>{v.location}</td><td>{v.department}</td>
            <td>{v.total_usable}</td><td>{v.assigned}</td><td>{v.available}</td><td>{v.reserved}</td><td>{v.utilization_pct}%</td></tr>
        ))}</tbody>
      </table>
    </>
  )
}

export default function App() {
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem('user') || 'null'))
  const [tab, setTab] = useState('ips')
  if (!user) return <Login onLogin={u => { localStorage.setItem('user', JSON.stringify(u)); setUser(u) }} />
  const admin = user.role === 'admin'
  return (
    <>
      <header>
        <b>IP Inventory</b>
        <nav>
          <button className={tab === 'ips' ? 'on' : ''} onClick={() => setTab('ips')}>IP Addresses</button>
          {admin && <button className={tab === 'vlans' ? 'on' : ''} onClick={() => setTab('vlans')}>VLANs</button>}
        </nav>
        <span>{user.full_name} ({user.role}) <button onClick={() => { localStorage.clear(); setUser(null) }}>Logout</button></span>
      </header>
      <main>{tab === 'vlans' && admin ? <VlanPage /> : <IpPage />}</main>
    </>
  )
}
