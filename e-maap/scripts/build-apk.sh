#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../apps/mobile"
: "${EXPO_PUBLIC_API_BASE_URL:?Set the phone-accessible backend URL, including /api/v1}"
command -v javac >/dev/null || { echo 'Install JDK 17 and set JAVA_HOME.'; exit 1; }
: "${ANDROID_HOME:?Install Android SDK and set ANDROID_HOME}"
npm ci
npx expo prebuild --platform android --no-install
cd android
./gradlew :app:assembleRelease
cp app/build/outputs/apk/release/app-release.apk ../../../../e-Maap-demo.apk
echo 'APK: e-Maap-demo.apk (demo signing; do not use as a production signing key)'
