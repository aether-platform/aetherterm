import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../pages/ControlCenterPage.vue'),
  },
  {
    path: '/term/control',
    name: 'ControlCenter',
    component: () => import('../pages/ControlCenterPage.vue'),
    meta: { title: 'AetherTerm - Control Center', requiresAuth: true },
  },
  {
    path: '/tmux/:session?',
    name: 'TmuxTerminal',
    component: () => import('../pages/TmuxPage.vue'),
    meta: { title: 'AetherTerm - tmux' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../pages/SettingsPage.vue'),
    meta: { title: 'AetherTerm - Settings' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
