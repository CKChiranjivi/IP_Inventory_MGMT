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

const FIELDS = ['department', 'room', 'equipment_id', 'equipment_name', 'cpu_serial', 'instrument_serial', 'user_name', 'remarks']

function Assign({ row, edit, onSave, onClose }) {
  const [d, setD] = useState(Object.fromEntries(FIELDS.map(k => [k, row[k] || ''])))
  return (
    <div className="modal"><div className="card">
      <h3>{edit ? 'Edit' : 'Assign'} {row.ip}</h3>
      <p className="muted">VLAN {row.vlan_id} · {row.location}</p>
      {FIELDS.map(k => <F key={k} label={k.replace('_', ' ')} value={d[k]} onChange={e => setD({ ...d, [k]: e.target.value })} />)}
      <div className="row">
        <button onClick={() => onSave(Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v.trim() || null])))}>{edit ? 'Save changes' : 'Assign'}</button>
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

  const act = async (path, body, method = 'POST') => {
    try { await api(path, method, body); setMsg(''); setSel(null) } catch (e) { setMsg(e.message) }
    load()
  }
  const flt = k => e => { setPage(1); setF({ ...f, [k]: e.target.value }) }
  const exportCsv = async () => {
    const p = new URLSearchParams()
    Object.entries(f).forEach(([k, v]) => v && p.set(k, v))
    const res = await fetch(`/api/export/ips.csv?${p}`, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })
    if (!res.ok) return setMsg('Export failed.')
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url; a.download = 'ip_inventory.csv'; a.click()
    URL.revokeObjectURL(url)
  }
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
        <button className="ghost" onClick={exportCsv}>Export CSV</button>
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
              {r.status === 'available' && <button onClick={() => setSel({ row: r })}>Assign</button>}
              {['assigned', 'inactive'].includes(r.status) && <button className="ghost" onClick={() => setSel({ row: r, edit: true })}>Edit</button>}
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
      {sel && <Assign row={sel.row} edit={sel.edit} onClose={() => setSel(null)}
        onSave={d => sel.edit ? act(`/api/ips/${sel.row.id}`, d, 'PATCH') : act(`/api/ips/${sel.row.id}/assign`, d)} />}
    </>
  )
}

function VlanPage() {
  const [list, setList] = useState([])
  const [d, setD] = useState({ vlan_id: '', name: '', network_address: '', cidr: '24', gateway: '', primary_dns: '', location: '', department: '', reserved_ips: '' })
  const [prev, setPrev] = useState(null)
  const [ev, setEv] = useState(null)
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
  const VF = ['vlan_id', 'name', 'location', 'department', 'description', 'primary_dns', 'secondary_dns']
  const saveEdit = async () => {
    try {
      const b = Object.fromEntries(VF.map(k => [k, ev[k] === '' || ev[k] == null ? null : k === 'vlan_id' ? +ev[k] : ev[k]]))
      setMsg({ text: (await api(`/api/vlans/${ev.id}`, 'PATCH', b)).message, ok: true }); setEv(null); load()
    } catch (e) { setMsg({ text: e.message }) }
  }

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
        <thead><tr>{['VLAN', 'Name', 'Network', 'Location', 'Dept', 'Total', 'Assigned', 'Available', 'Reserved', 'Used %', ''].map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{list.map(v => (
          <tr key={v.id}><td>{v.vlan_id}</td><td>{v.name}</td><td>{v.network}/{v.cidr}</td><td>{v.location}</td><td>{v.department}</td>
            <td>{v.total_usable}</td><td>{v.assigned}</td><td>{v.available}</td><td>{v.reserved}</td><td>{v.utilization_pct}%</td><td><button className="ghost" onClick={() => api(`/api/vlans/${v.id}`).then(d => setEv({ ...d, id: v.id, network: v.network, cidr: v.cidr })).catch(e => setMsg({ text: e.message }))}>Edit</button></td></tr>
        ))}</tbody>
      </table>
      {ev && (
        <div className="modal"><div className="card">
          <h3>Edit VLAN {ev.vlan_id}</h3>
          <p className="muted">{ev.network}/{ev.cidr} · network, CIDR and gateway cannot be changed</p>
          {VF.map(k => <F key={k} label={k.replace('_', ' ')} value={ev[k] ?? ''} onChange={e => setEv({ ...ev, [k]: e.target.value })} />)}
          <div className="row"><button onClick={saveEdit}>Save changes</button><button className="ghost" onClick={() => setEv(null)}>Cancel</button></div>
        </div></div>
      )}
    </>
  )
}

function UsersPage({ me }) {
  const blank = { username: '', full_name: '', email: '', password: '', role: 'user' }
  const [list, setList] = useState([])
  const [d, setD] = useState(blank)
  const [msg, setMsg] = useState({ text: '', ok: false })
  const load = () => api('/api/users').then(setList).catch(e => setMsg({ text: e.message }))
  useEffect(() => { load() }, [])
  const run = async (fn, ok) => {
    try { await fn(); setMsg({ text: ok, ok: true }); load() } catch (e) { setMsg({ text: e.message }) }
  }
  const add = () => run(async () => { await api('/api/users', 'POST', { ...d, email: d.email || null }); setD(blank) }, 'User created.')
  const patch = (u, body) => run(() => api(`/api/users/${u.id}`, 'PATCH', body), 'User updated.')
  const reset = u => {
    const pw = window.prompt(`New password for ${u.username} (8-64 characters):`)
    if (pw) run(() => api(`/api/users/${u.id}/password`, 'POST', { new_password: pw }), `Password reset for ${u.username}.`)
  }
  return (
    <>
      <div className="card">
        <h3>Add user</h3>
        <div className="grid">
          <F label="Username" value={d.username} onChange={e => setD({ ...d, username: e.target.value })} />
          <F label="Full name" value={d.full_name} onChange={e => setD({ ...d, full_name: e.target.value })} />
          <F label="Email" value={d.email} onChange={e => setD({ ...d, email: e.target.value })} />
          <F label="Password (min 8)" type="password" value={d.password} onChange={e => setD({ ...d, password: e.target.value })} />
          <label className="f">Role<select value={d.role} onChange={e => setD({ ...d, role: e.target.value })}><option value="user">Normal User</option><option value="admin">Admin</option></select></label>
        </div>
        <div className="row"><button onClick={add}>Add user</button></div>
        {msg.text && <div className={msg.ok ? 'ok' : 'err'}>{msg.text}</div>}
      </div>
      <table>
        <thead><tr>{['Username', 'Name', 'Email', 'Role', 'Status', 'Created', ''].map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{list.map(u => (
          <tr key={u.id}>
            <td>{u.username}</td><td>{u.full_name}</td><td>{u.email}</td><td>{u.role}</td>
            <td>{u.is_active ? 'Active' : 'Inactive'}</td><td>{String(u.created_at).slice(0, 10)}</td>
            <td className="acts">
              <button className="ghost" onClick={() => reset(u)}>Reset password</button>
              {u.id !== me.id && <>
                <button className="ghost" onClick={() => patch(u, { role: u.role === 'admin' ? 'user' : 'admin' })}>Make {u.role === 'admin' ? 'user' : 'admin'}</button>
                <button className={u.is_active ? 'danger' : ''} onClick={() => patch(u, { is_active: !u.is_active })}>{u.is_active ? 'Deactivate' : 'Activate'}</button>
              </>}
            </td>
          </tr>
        ))}</tbody>
      </table>
    </>
  )
}

function ChangePassword({ onClose }) {
  const blank = { current_password: '', new_password: '', confirm: '' }
  const [d, setD] = useState(blank)
  const [msg, setMsg] = useState({ text: '', ok: false })
  const set = k => e => setD({ ...d, [k]: e.target.value })
  const save = async () => {
    if (d.new_password !== d.confirm) return setMsg({ text: 'New passwords do not match.' })
    try {
      await api('/api/auth/change-password', 'POST', { current_password: d.current_password, new_password: d.new_password })
      setMsg({ text: 'Password changed.', ok: true }); setD(blank)
    } catch (e) { setMsg({ text: e.message }) }
  }
  return (
    <div className="modal"><div className="card">
      <h3>Change password</h3>
      <F label="Current password" type="password" value={d.current_password} onChange={set('current_password')} />
      <F label="New password (8-64 characters)" type="password" value={d.new_password} onChange={set('new_password')} />
      <F label="Confirm new password" type="password" value={d.confirm} onChange={set('confirm')} />
      {msg.text && <div className={msg.ok ? 'ok' : 'err'}>{msg.text}</div>}
      <div className="row"><button onClick={save}>Save</button><button className="ghost" onClick={onClose}>Close</button></div>
    </div></div>
  )
}

const ACTIONS = ['VLAN_CREATE', 'VLAN_EDIT', 'IP_ASSIGN', 'IP_RELEASE', 'IP_STATUS_CHANGE', 'IP_EDIT', 'USER_CREATE', 'USER_EDIT', 'USER_PASSWORD_RESET', 'USER_PASSWORD_CHANGE']

function changes(a) {
  const o = a.old_value || {}, n = a.new_value || {}
  return Object.keys(n)
    .filter(k => JSON.stringify(o[k]) !== JSON.stringify(n[k]))
    .map(k => (k in o ? `${k}: ${o[k] ?? '-'} → ${n[k] ?? '-'}` : `${k}: ${n[k] ?? '-'}`))
    .join(' · ')
}

function AuditPage() {
  const [f, setF] = useState({ action: '', entity_type: '' })
  const [page, setPage] = useState(1)
  const [tick, setTick] = useState(0)
  const [data, setData] = useState({ items: [], total: 0 })
  const [err, setErr] = useState('')
  useEffect(() => {
    const p = new URLSearchParams({ page, page_size: 25 })
    Object.entries(f).forEach(([k, v]) => v && p.set(k, v))
    api(`/api/audit?${p}`).then(d => { setData(d); setErr('') }).catch(e => setErr(e.message))
  }, [f, page, tick])
  const flt = k => e => { setPage(1); setF({ ...f, [k]: e.target.value }) }
  return (
    <>
      <div className="bar">
        <select value={f.action} onChange={flt('action')}>
          <option value="">All actions</option>
          {ACTIONS.map(a => <option key={a}>{a}</option>)}
        </select>
        <select value={f.entity_type} onChange={flt('entity_type')}>
          <option value="">All types</option>
          {['ip', 'vlan', 'user'].map(t => <option key={t}>{t}</option>)}
        </select>
        <button className="ghost" onClick={() => setTick(tick + 1)}>Refresh</button>
      </div>
      {err && <div className="err">{err}</div>}
      <table>
        <thead><tr>{['Time', 'Changed by', 'Action', 'Target', 'Details'].map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{data.items.map(a => (
          <tr key={a.id}>
            <td>{String(a.created_at).replace('T', ' ').slice(0, 19)}</td>
            <td>{a.changed_by_name || a.changed_by}<br /><small className="muted">{a.changed_by}</small></td>
            <td>{a.action}</td><td>{a.target}</td>
            <td><small>{changes(a)}</small></td>
          </tr>
        ))}</tbody>
      </table>
      <div className="row">
        <button className="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
        <span>Page {page} · {data.total} entries</span>
        <button className="ghost" disabled={page * 25 >= data.total} onClick={() => setPage(page + 1)}>Next</button>
      </div>
    </>
  )
}

function Dashboard() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/dashboard').then(setD).catch(e => setErr(e.message)) }, [])
  if (err) return <div className="err">{err}</div>
  if (!d) return <p className="muted">Loading...</p>
  const t = d.totals
  const color = p => (p >= 90 ? '#dc2626' : p >= 75 ? '#f59e0b' : '#2563eb')
  const stats = [['Total IPs', t.total], ['Assigned', t.assigned], ['Available', t.available], ['Reserved', t.reserved], ['Inactive', t.inactive], ['Utilization', `${t.utilization_pct}%`]]
  return (
    <>
      <div className="stats">{stats.map(([l, v]) => <div key={l} className="card stat"><span className="muted">{l}</span><b>{v}</b></div>)}</div>
      <table>
        <thead><tr>{['VLAN', 'Name', 'Network', 'Location', 'Dept', 'Assigned / Total', 'Available', 'Reserved', 'Utilization'].map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{d.vlans.map(v => (
          <tr key={v.id}>
            <td>{v.vlan_id}</td><td>{v.name}</td><td>{v.network}/{v.cidr}</td><td>{v.location}</td><td>{v.department}</td>
            <td>{v.assigned} / {v.total}</td><td>{v.available}</td><td>{v.reserved}</td>
            <td><div className="meter"><i style={{ width: `${Math.min(v.utilization_pct, 100)}%`, background: color(v.utilization_pct) }} /></div><small>{v.utilization_pct}%</small></td>
          </tr>
        ))}</tbody>
      </table>
    </>
  )
}

export default function App() {
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem('user') || 'null'))
  const [tab, setTab] = useState('dashboard')
  const [pw, setPw] = useState(false)
  if (!user) return <Login onLogin={u => { localStorage.setItem('user', JSON.stringify(u)); setUser(u) }} />
  const admin = user.role === 'admin'
  return (
    <>
      <header>
        <b>IP Inventory</b>
        <nav>
          <button className={tab === 'dashboard' ? 'on' : ''} onClick={() => setTab('dashboard')}>Dashboard</button>
          <button className={tab === 'ips' ? 'on' : ''} onClick={() => setTab('ips')}>IP Addresses</button>
          {admin && <button className={tab === 'vlans' ? 'on' : ''} onClick={() => setTab('vlans')}>VLANs</button>}
          {admin && <button className={tab === 'users' ? 'on' : ''} onClick={() => setTab('users')}>Users</button>}
          {admin && <button className={tab === 'audit' ? 'on' : ''} onClick={() => setTab('audit')}>Audit Log</button>}
        </nav>
        <span>{user.full_name} ({user.role}) <button onClick={() => setPw(true)}>Change password</button> <button onClick={() => { localStorage.clear(); setUser(null) }}>Logout</button></span>
      </header>
      <main>{tab === 'dashboard' ? <Dashboard /> : tab === 'audit' && admin ? <AuditPage /> : tab === 'users' && admin ? <UsersPage me={user} /> : tab === 'vlans' && admin ? <VlanPage /> : <IpPage />}</main>
      {pw && <ChangePassword onClose={() => setPw(false)} />}
    </>
  )
}
