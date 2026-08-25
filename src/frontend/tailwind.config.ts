import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        adequate: { DEFAULT: '#16a34a', light: '#dcfce7' },
        limited: { DEFAULT: '#ca8a04', light: '#fef9c3' },
        insufficient: { DEFAULT: '#dc2626', light: '#fee2e2' },
      },
    },
  },
  plugins: [],
}
export default config
