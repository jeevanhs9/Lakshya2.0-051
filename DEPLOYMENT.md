# FarmLink AI - Vercel Deployment Guide

## Prerequisites
- [Vercel Account](https://vercel.com/signup)
- [Vercel CLI](https://vercel.com/docs/cli) installed (optional)
- Git repository

## Project Structure for Vercel

```
farmlink-ai/
├── api/                    # Serverless functions
│   └── index.py           # Python Flask API entry point
├── server/                 # Backend Flask application
│   ├── app.py             # Main Flask app
│   ├── models.py          # Database models
│   ├── seed.py            # Database seeder
│   └── *.py               # Other modules
├── src/                    # React frontend
├── public/                 # Static assets
├── dist/                   # Build output (auto-generated)
├── package.json           # Node.js dependencies
├── requirements.txt       # Python dependencies
├── vercel.json            # Vercel configuration
└── vite.config.js         # Vite config
```

## Deployment Steps

### Method 1: Deploy via Vercel Dashboard (Easiest)

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-github-repo-url>
   git push -u origin main
   ```

2. **Import to Vercel**
   - Go to [Vercel Dashboard](https://vercel.com/dashboard)
   - Click "Add New Project"
   - Import your GitHub repository
   - Vercel will auto-detect the framework (Vite)

3. **Configure Build Settings** (if not auto-detected)
   - Framework Preset: `Vite`
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Install Command: `npm install`

4. **Deploy**
   - Click "Deploy"
   - Wait for build to complete
   - Your app will be live at `https://your-project.vercel.app`

### Method 2: Deploy via Vercel CLI

1. **Install Vercel CLI**
   ```bash
   npm install -g vercel
   ```

2. **Login to Vercel**
   ```bash
   vercel login
   ```

3. **Deploy**
   ```bash
   # First deployment
   vercel
   
   # Follow the prompts:
   # - Set up and deploy? Yes
   # - Which scope? Select your account
   # - Link to existing project? No
   # - Project name? farmlink-ai
   # - Directory? ./
   # - Override settings? No
   ```

4. **Deploy to Production**
   ```bash
   vercel --prod
   ```

## Environment Variables

If you need environment variables, add them in Vercel Dashboard:

1. Go to Project Settings → Environment Variables
2. Add variables:
   - `DATABASE_URL` (if using external database)
   - `FLASK_ENV=production`
   - Any API keys

## Important Notes

### SQLite Database
⚠️ **Warning**: Vercel serverless functions are stateless. SQLite database will be reset on each deployment.

**Solutions**:
1. **Use PostgreSQL** (Recommended for production)
   - Use [Vercel Postgres](https://vercel.com/docs/storage/vercel-postgres)
   - Or external service like [Neon](https://neon.tech/), [Supabase](https://supabase.com/)
   
2. **Keep SQLite for Demo** (Current setup)
   - Database reseeds on each deployment
   - Good for testing/demo purposes

### API Routes
- Frontend: `https://your-project.vercel.app/`
- API: `https://your-project.vercel.app/api/*`

### Cold Starts
- First API request may be slow (cold start)
- Subsequent requests will be faster

## Updating Your Deployment

### Automatic Deployments
- Push to `main` branch → Auto-deploys to production
- Push to other branches → Creates preview deployments

### Manual Deployment
```bash
vercel --prod
```

## Troubleshooting

### Build Fails
1. Check build logs in Vercel Dashboard
2. Ensure all dependencies are in `package.json`
3. Test build locally: `npm run build`

### API Not Working
1. Check Python version in `vercel.json` matches requirements
2. Verify `requirements.txt` has all dependencies
3. Check API logs in Vercel Dashboard

### Frontend Not Loading
1. Ensure `dist` directory is being created
2. Check `vercel.json` routes configuration
3. Verify `index.html` exists in build output

## Local Testing Before Deployment

```bash
# Test frontend build
npm run build
npm run preview

# Test backend
cd server
python app.py
```

## Support

- [Vercel Documentation](https://vercel.com/docs)
- [Vercel Community](https://github.com/vercel/vercel/discussions)
- [Flask on Vercel Guide](https://vercel.com/guides/using-flask-with-vercel)

## Project URLs (After Deployment)

- Production: `https://farmlink-ai.vercel.app` (your actual URL will be different)
- API Health Check: `https://farmlink-ai.vercel.app/api/health`
