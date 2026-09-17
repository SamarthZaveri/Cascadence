import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'

// Real routes (/login, /companies/:id, /simulate, /alerts, /backtests,
// /settings/api-keys, /settings/workspace) get added per PRD.md §9 as each is built.
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
      </Routes>
    </BrowserRouter>
  )
}
