import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import PortalRouter from './PortalRouter.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <PortalRouter />
  </StrictMode>,
)
