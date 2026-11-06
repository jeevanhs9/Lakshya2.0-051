# FarmLink AI - Quick Vercel Deployment Script
# Run this script to deploy to Vercel

Write-Host "🚀 FarmLink AI - Vercel Deployment" -ForegroundColor Cyan
Write-Host "===================================`n" -ForegroundColor Cyan

# Check if Vercel CLI is installed
$vercelInstalled = Get-Command vercel -ErrorAction SilentlyContinue

if (-not $vercelInstalled) {
    Write-Host "⚠️  Vercel CLI not found. Installing..." -ForegroundColor Yellow
    npm install -g vercel
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to install Vercel CLI. Please install manually:" -ForegroundColor Red
        Write-Host "   npm install -g vercel`n" -ForegroundColor White
        exit 1
    }
}

Write-Host "✅ Vercel CLI found`n" -ForegroundColor Green

# Check if logged in
Write-Host "📝 Checking Vercel authentication..." -ForegroundColor Cyan
vercel whoami 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "🔑 Please login to Vercel..." -ForegroundColor Yellow
    vercel login
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to login. Please try again.`n" -ForegroundColor Red
        exit 1
    }
}

Write-Host "✅ Authenticated`n" -ForegroundColor Green

# Build the project
Write-Host "🔨 Building frontend..." -ForegroundColor Cyan
npm run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Build failed. Please fix errors and try again.`n" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Build successful`n" -ForegroundColor Green

# Deploy to Vercel
Write-Host "🚀 Deploying to Vercel..." -ForegroundColor Cyan
Write-Host "(This may take a few minutes...)`n" -ForegroundColor Yellow

vercel --prod

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Deployment successful! 🎉" -ForegroundColor Green
    Write-Host "Your app is now live!`n" -ForegroundColor Green
} else {
    Write-Host "`n❌ Deployment failed. Check the logs above.`n" -ForegroundColor Red
    exit 1
}
