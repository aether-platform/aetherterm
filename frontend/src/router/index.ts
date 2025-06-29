import { createRouter, createWebHistory } from 'vue-router'
import TerminalComponent from '../components/TerminalComponent.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'terminal',
      component: TerminalComponent
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ],
})

export default router
