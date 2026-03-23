# Deploy Web MVP (Firebase Hosting + Cloud Run)

## 1) Build frontend
1. `cd web`
2. `npm install`
3. `npm run build`

## 2) Build and deploy API to Cloud Run
1. `gcloud builds submit --tag gcr.io/<PROJECT_ID>/tt133-mvp-api .`
2. `gcloud run deploy tt133-mvp-api --image gcr.io/<PROJECT_ID>/tt133-mvp-api --region asia-southeast1 --allow-unauthenticated`

## 3) Configure Firebase
1. Update `.firebaserc` with your Firebase project id.
2. Ensure `firebase.json` rewrite serviceId and region match Cloud Run deployment.
3. `firebase deploy --only hosting`

## 4) MVP login
- API uses `/api/auth/login-demo` for demo login.
- First login requires creating company profile before posting events.
