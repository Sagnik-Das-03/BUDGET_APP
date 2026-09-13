import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { App } from './App.tsx'
import { LanPasswordGate } from './components/LanPasswordGate.tsx'
import { ThemeProvider } from './components/theme-provider'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <LanPasswordGate>
          <App />
        </LanPasswordGate>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
