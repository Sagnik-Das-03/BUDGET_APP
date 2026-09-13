package com.sd.budgetdashboard

import android.content.Context
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.Bundle
import android.util.Log
import androidx.activity.compose.setContent
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import java.net.Inet4Address
import java.net.NetworkInterface

// FragmentActivity, not ComponentActivity - BiometricPrompt requires it.
class MainActivity : FragmentActivity() {

    // Re-locks whenever the app leaves the foreground (see onPause) - a
    // banking-app-style re-prompt, not just a one-time gate at process
    // start, since the whole point is that picking up the phone later
    // shouldn't land straight back on this screen unlocked.
    private val unlocked = mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            if (unlocked.value) {
                ServerDashboard()
            } else {
                LockScreen(onUnlock = { authenticate() })
            }
        }
    }

    override fun onStart() {
        super.onStart()
        if (!unlocked.value) authenticate()
    }

    override fun onPause() {
        super.onPause()
        // Re-lock on the way out - authenticate() runs again in onStart the
        // next time this activity comes back to the foreground.
        unlocked.value = false
    }

    private fun authenticate() {
        val biometricManager = BiometricManager.from(this)
        val allowedAuthenticators = BIOMETRIC_WEAK or DEVICE_CREDENTIAL
        when (biometricManager.canAuthenticate(allowedAuthenticators)) {
            BiometricManager.BIOMETRIC_SUCCESS -> showBiometricPrompt(allowedAuthenticators)
            else -> {
                // No fingerprint/face enrolled and no screen lock set up at
                // all - this is a personal, single-owner phone, so fail
                // OPEN rather than permanently locking the owner out of
                // their own app over a device they haven't configured a
                // lock on yet.
                Log.w("MainActivity", "Biometric/device-credential auth unavailable - skipping lock")
                unlocked.value = true
            }
        }
    }

    private fun showBiometricPrompt(allowedAuthenticators: Int) {
        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(
            this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    unlocked.value = true
                }
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    // User cancelled, or too many failed attempts, etc. -
                    // stay locked; LockScreen's button lets them retry.
                }
                override fun onAuthenticationFailed() {
                    // A single wrong fingerprint/face match - the system
                    // prompt itself already handles retry UI, nothing to
                    // do here beyond staying locked.
                }
            },
        )
        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Unlock Budget Dashboard")
            .setSubtitle("Authenticate to view the server controls")
            .setAllowedAuthenticators(allowedAuthenticators)
            .build()
        prompt.authenticate(promptInfo)
    }

    private fun startServer() {
        val intent = Intent(this, ServerService::class.java)
        startForegroundService(intent)
    }

    private fun stopServer() {
        val intent = Intent(this, ServerService::class.java)
        stopService(intent)
    }

    @Composable
    fun LockScreen(onUnlock: () -> Unit) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background
        ) {
            Column(
                modifier = Modifier.fillMaxSize().padding(24.dp),
                verticalArrangement = Arrangement.Center
            ) {
                Text(text = "Budget Dashboard", style = MaterialTheme.typography.headlineMedium)
                Spacer(modifier = Modifier.height(8.dp))
                Text(text = "Locked - authenticate to continue", style = MaterialTheme.typography.bodyLarge)
                Spacer(modifier = Modifier.height(24.dp))
                Button(onClick = onUnlock) {
                    Text("Unlock")
                }
            }
        }
    }

    @Composable
    fun ServerDashboard() {
        var serverRunning by remember { mutableStateOf(false) }

        val ipAddress = remember {
            getLocalIpAddress()
        }

        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(24.dp),
                verticalArrangement = Arrangement.Top
            ) {

                Text(
                    text = "Budget Dashboard",
                    style = MaterialTheme.typography.headlineMedium
                )

                Text(
                    text = "Local server host",
                    style = MaterialTheme.typography.bodyLarge
                )

                Spacer(modifier = Modifier.height(24.dp))

                Card(
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp)
                    ) {
                        Text(
                            text = "Server Status",
                            style = MaterialTheme.typography.titleLarge
                        )

                        Spacer(modifier = Modifier.height(12.dp))

                        Text(
                            text = if (serverRunning) {
                                "● Running"
                            } else {
                                "● Stopped"
                            }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                Card(
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp)
                    ) {
                        Text(
                            text = "Server Information",
                            style = MaterialTheme.typography.titleLarge
                        )

                        Spacer(modifier = Modifier.height(12.dp))

                        Text("Host: 0.0.0.0")
                        Text("Port: 8000")
                        Text("Runtime: Python 3.13")
                        Text("Framework: FastAPI")
                        Text("Server: Uvicorn")

                        Spacer(modifier = Modifier.height(16.dp))

                        Text(
                            text = "LAN Address",
                            style = MaterialTheme.typography.titleMedium
                        )

                        Spacer(modifier = Modifier.height(4.dp))

                        Text(
                            text = "$ipAddress:8000",
                            style = MaterialTheme.typography.headlineSmall
                        )

                        Spacer(modifier = Modifier.height(4.dp))

                        Text(
                            text = "Open this address on another device " +
                                    "connected to the same Wi-Fi."
                        )
                    }
                }

                Spacer(modifier = Modifier.height(24.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {

                    Button(
                        onClick = {
                            startServer()
                            serverRunning = true
                        },
                        enabled = !serverRunning,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Start Server")
                    }

                    Button(
                        onClick = {
                            stopServer()
                            serverRunning = false
                        },
                        enabled = serverRunning,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Stop Server")
                    }
                }
            }
        }
    }
}

private fun getLocalIpAddress(): String {
    return try {
        val interfaces = NetworkInterface.getNetworkInterfaces()

        while (interfaces.hasMoreElements()) {
            val networkInterface = interfaces.nextElement()

            if (!networkInterface.isUp || networkInterface.isLoopback) {
                continue
            }

            val addresses = networkInterface.inetAddresses

            while (addresses.hasMoreElements()) {
                val address = addresses.nextElement()

                if (address is Inet4Address && !address.isLoopbackAddress) {
                    return address.hostAddress ?: "Unknown"
                }
            }
        }

        "Not connected"
    } catch (e: Exception) {
        "Unknown"
    }
}
