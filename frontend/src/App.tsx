import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AuthProvider } from './auth/AuthProvider'
import { GuestOnly, RequireAuth } from './auth/guards'
import { AppLayout } from './components/AppLayout'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { ReviewPage } from './pages/ReviewPage'
import { TalkListPage } from './pages/TalkListPage'
import { TalkPage } from './pages/TalkPage'
import { TopicPage } from './pages/TopicPage'
import { VocabularyPage } from './pages/VocabularyPage'
import { ProfilePage } from './pages/ProfilePage'
import { PlacementPage } from './pages/PlacementPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<GuestOnly />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
          </Route>
          <Route element={<RequireAuth />}>
            <Route element={<AppLayout />}>
              <Route path="/" element={<HomePage />} />
              <Route path="/topics/:topicId" element={<TopicPage />} />
              <Route path="/vocabulary" element={<VocabularyPage />} />
              <Route path="/review" element={<ReviewPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/placement" element={<PlacementPage />} />
              <Route path="/talk" element={<TalkListPage />} />
              <Route path="/talk/:dialogId" element={<TalkPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
