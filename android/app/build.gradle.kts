plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.example.nailar"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.example.nailar"
        minSdk = 24            // MediaPipe Tasks 최소 요구
        targetSdk = 34
        versionCode = 1
        versionName = "0.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    // .task/.onnx 모델은 압축하면 mmap/로딩이 안 되므로 비압축
    androidResources {
        noCompress += "task"
        noCompress += "onnx"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")

    // CameraX (Preview + ImageAnalysis) — PC video_source 역할
    val camerax = "1.3.4"
    implementation("androidx.camera:camera-core:$camerax")
    implementation("androidx.camera:camera-camera2:$camerax")
    implementation("androidx.camera:camera-lifecycle:$camerax")
    implementation("androidx.camera:camera-view:$camerax")

    // MediaPipe Tasks Vision (HandLandmarker) — PC hand_landmarks 역할
    implementation("com.google.mediapipe:tasks-vision:0.10.14")

    // onnxruntime-android — 온디바이스 YOLOv8-seg 손톱검출(에지 서버 모드). NNAPI EP 내장.
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.20.0")
}
