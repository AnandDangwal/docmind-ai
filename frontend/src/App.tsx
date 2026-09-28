import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { AuthProvider } from "@/lib/auth"
import { ProtectedRoute } from "@/components/ProtectedRoute"
import LoginPage from "@/pages/LoginPage"
import ThreadListPage from "@/pages/ThreadListPage"
import ThreadPage from "@/pages/ThreadPage"

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <ThreadListPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/threads/:id"
            element={
              <ProtectedRoute>
                <ThreadPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
