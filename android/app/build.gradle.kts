plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    id("com.chaquo.python")
}
chaquopy {
    defaultConfig {
        version = "3.13"
        buildPython("py", "-3.13")

        pip {
            // Matches budget_tracker/android_dashboard/requirements.txt -
            // deliberately NOT the desktop app's full requirements.txt
            // (no SQLAlchemy, no litert-lm-api - this build is read-only,
            // no local database, no LLM features).
            install("fastapi==0.115.6")
            install("uvicorn==0.34.0")
            install("google-api-python-client==2.158.0")
            install("google-auth==2.38.0")
        }
    }
}

android {
    namespace = "com.sd.budgetdashboard"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.sd.budgetdashboard"
        minSdk = 24
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}