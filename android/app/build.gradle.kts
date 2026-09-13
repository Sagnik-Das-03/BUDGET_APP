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
            // The REAL backend (see sync_android.bat, which copies
            // backend/app/ here as-is) now runs on this host too - this is
            // backend/requirements.txt, trimmed to what it actually needs:
            // pydantic<2 instead of ==2.10.6 (v2 depends on pydantic-core,
            // a Rust extension with no Android wheel and no Rust toolchain
            // in Chaquopy to build one - see app/_pydantic_compat.py for
            // how the same source tree supports both), no pydantic-settings
            // (v1's BaseSettings lives in pydantic itself), no typer/
            // openpyxl (app/cli.py and scripts/ aren't copied here at all),
            // no litert-lm-api (no local LLM on this build - app/llm/router.py
            // already degrades gracefully without it), plain uvicorn not
            // uvicorn[standard] (the extras need C extensions this app
            // never uses - see the original scoping in git history).
            install("fastapi==0.115.6")
            install("uvicorn==0.34.0")
            install("sqlalchemy==2.0.41")
            install("pydantic<2")
            install("google-api-python-client==2.158.0")
            install("google-auth==2.38.0")
            install("apscheduler==3.11.0")
            install("python-dotenv==1.0.1")
            install("python-multipart==0.0.20")
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
    implementation(libs.androidx.biometric)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}