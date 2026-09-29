import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { AuthProvider } from "@/lib/auth"
import { ProtectedRoute } from "@/components/ProtectedRoute"
import { AppShell } from "@/components/layout/AppShell"
import LoginPage from "@/pages/LoginPage"
import EmptyThreadPage from "@/pages/EmptyThreadPage"
import ThreadPage from "@/pages/ThreadPage"

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<EmptyThreadPage />} />
            <Route path="/threads/:id" element={<ThreadPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
