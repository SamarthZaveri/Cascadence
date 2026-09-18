import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route
          path="*"
          element={
            <main>
              <h1>Page not found</h1>
              <a href="/dashboard">Open dashboard</a>
            </main>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
