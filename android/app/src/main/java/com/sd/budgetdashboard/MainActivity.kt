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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.chaquo.python.PyException
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONArray
import java.net.Inet4Address
import java.net.NetworkInterface

// FragmentActivity, not ComponentActivity - BiometricPrompt requires it.
class MainActivity : FragmentActivity() {

    // Re-locks whenever the app leaves the foreground (see onPause) - a
    // banking-app-style re-prompt, not just a one-time gate at process
    // start, since the whole point is that picking up the phone later
    // shouldn't land straight back on this screen unlocked.
    private val unlocked = mutableStateOf(false)

    // The LAN password (see auth_glue.py) is separate from the
    // biometric lock above: the biometric lock guards this control screen on
    // the phone itself, the LAN password guards the actual HTTP server every
    // other device on the Wi-Fi talks to. Server.py's middleware fails
    // CLOSED until one is set, so this screen is shown ahead of the
    // dashboard controls the very first time, and reachable again afterwards
    // to change it.
    private val passwordSet = mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Started here (not only in ServerService) so the password/viewer
        // screens below work even before the server has ever been started -
        // Chaquopy's interpreter is one process-wide instance either way.
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        setContent {
            when {
                !unlocked.value -> LockScreen(onUnlock = { authenticate() })
                !passwordSet.value -> SetPasswordScreen(
                    isChange = false,
                    onSaved = { passwordSet.value = true },
                    onCancel = null,
                )
                else -> ServerDashboard()
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
                onUnlocked()
            }
        }
    }

    private fun showBiometricPrompt(allowedAuthenticators: Int) {
        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(
            this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    onUnlocked()
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

    private fun onUnlocked() {
        unlocked.value = true
        passwordSet.value = isPasswordSetPy()
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
    fun SetPasswordScreen(isChange: Boolean, onSaved: () -> Unit, onCancel: (() -> Unit)?) {
        var password by remember { mutableStateOf("") }
        var confirm by remember { mutableStateOf("") }
        var error by remember { mutableStateOf<String?>(null) }

        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            Column(
                modifier = Modifier.fillMaxSize().padding(24.dp),
                verticalArrangement = Arrangement.Center,
            ) {
                Text(
                    text = if (isChange) "Change LAN Password" else "Set a LAN Password",
                    style = MaterialTheme.typography.headlineSmall,
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Anyone on your Wi-Fi who knows this password can open your dashboard in a " +
                        "browser. It's separate from unlocking this app, and required before the server " +
                        "will respond to anything.",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(modifier = Modifier.height(20.dp))
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it; error = null },
                    label = { Text("New password") },
                    visualTransformation = PasswordVisualTransformation(),
                    // Without this, the keyboard doesn't know it's a password
                    // field and can silently auto-capitalize/autocorrect what
                    // you type - the saved password then no longer matches
                    // what you type back into the browser's login prompt.
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = confirm,
                    onValueChange = { confirm = it; error = null },
                    label = { Text("Confirm password") },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                error?.let {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
                Spacer(modifier = Modifier.height(16.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Button(onClick = {
                        when {
                            password.length < 4 -> error = "Password must be at least 4 characters"
                            password != confirm -> error = "Passwords don't match"
                            else -> try {
                                setPasswordPy(password)
                                onSaved()
                            } catch (e: PyException) {
                                error = e.message ?: "Couldn't save the password"
                            }
                        }
                    }) { Text("Save") }
                    if (onCancel != null) {
                        Button(onClick = onCancel) { Text("Cancel") }
                    }
                }
            }
        }
    }

    @Composable
    fun ViewersSection() {
        // Read-only by design: onboarding a person (picking a name, linking
        // their spreadsheet) only ever happens on the desktop app, which
        // publishes the list this reads (see backend/app/sync/reports.py's
        // regenerate_viewer_manifest) - there is deliberately no add/remove
        // here, just "look" and "switch which one I'm looking at". A viewer
        // with a desktop password requires it here too (see viewers.py's
        // activate_viewer) - otherwise the LAN password alone would let
        // anyone on the Wi-Fi see every viewer, not just the ones without
        // their own password.
        var viewersJson by remember { mutableStateOf(listViewersPy()) }
        var error by remember { mutableStateOf<String?>(null) }
        var active by remember { mutableStateOf<String?>(null) }
        var pendingName by remember { mutableStateOf<String?>(null) }
        var switchPassword by remember { mutableStateOf("") }

        data class ViewerRow(val name: String, val hasPassword: Boolean)
        val viewerRows = remember(viewersJson) {
            val arr = JSONArray(viewersJson)
            (0 until arr.length()).map { i ->
                val obj = arr.getJSONObject(i)
                ViewerRow(obj.getString("name"), obj.getBoolean("has_password"))
            }
        }

        fun trySwitch(name: String, password: String) {
            try {
                activateViewerPy(name, password)
                active = name
                error = null
                pendingName = null
                switchPassword = ""
            } catch (e: PyException) {
                error = e.message ?: "Couldn't switch to $name"
            }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text("Viewers", style = MaterialTheme.typography.titleLarge)
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Published from the desktop app - onboarding a person happens there, not " +
                        "here. Each gets its own isolated local cache, refreshed automatically.",
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(modifier = Modifier.height(12.dp))
                if (viewerRows.isEmpty()) {
                    Text(
                        "No viewers yet - start the server once to pull the list, or check that a " +
                            "person has been onboarded on the desktop app.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                } else {
                    viewerRows.forEach { row ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(row.name, style = MaterialTheme.typography.bodyLarge)
                            TextButton(onClick = {
                                error = null
                                if (row.hasPassword) {
                                    pendingName = row.name
                                    switchPassword = ""
                                } else {
                                    trySwitch(row.name, "")
                                }
                            }) { Text(if (active == row.name) "Viewing" else "View") }
                        }
                    }
                }
                pendingName?.let { name ->
                    Spacer(modifier = Modifier.height(8.dp))
                    Column(modifier = Modifier.padding(top = 4.dp)) {
                        Text("Password for $name", style = MaterialTheme.typography.bodySmall)
                        Spacer(modifier = Modifier.height(4.dp))
                        OutlinedTextField(
                            value = switchPassword,
                            onValueChange = { switchPassword = it },
                            visualTransformation = PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Button(onClick = { trySwitch(name, switchPassword) }) { Text("Switch") }
                            Button(onClick = { pendingName = null; error = null }) { Text("Cancel") }
                        }
                    }
                }
                error?.let {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
                Spacer(modifier = Modifier.height(8.dp))
                TextButton(onClick = { viewersJson = listViewersPy() }) { Text("Refresh list") }
            }
        }
    }

    @Composable
    fun ServerDashboard() {
        // Read from ServerService.isRunning (not a local "did I just click
        // Start" flag) so this reflects reality even after the Activity is
        // recreated while the foreground service kept running - see that
        // companion property's own comment for why a plain var is safe here.
        var serverRunning by remember { mutableStateOf(ServerService.isRunning) }
        var changingPassword by remember { mutableStateOf(false) }
        val clipboard = LocalClipboardManager.current

        val ipAddress = remember {
            getLocalIpAddress()
        }

        if (changingPassword) {
            SetPasswordScreen(
                isChange = true,
                onSaved = { changingPassword = false },
                onCancel = { changingPassword = false },
            )
            return
        }

        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
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
                            text = if (serverRunning) "● Running" else "● Stopped",
                            color = if (serverRunning) Color(0xFF2E7D32) else Color(0xFFC62828),
                        )

                        Spacer(modifier = Modifier.height(16.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            Button(
                                onClick = {
                                    startServer()
                                    serverRunning = true
                                },
                                enabled = !serverRunning,
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = Color(0xFF2E7D32),
                                    contentColor = Color.White,
                                ),
                                modifier = Modifier.weight(1f),
                            ) { Text("Start Server") }

                            Button(
                                onClick = {
                                    stopServer()
                                    serverRunning = false
                                },
                                enabled = serverRunning,
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = Color(0xFFC62828),
                                    contentColor = Color.White,
                                ),
                                modifier = Modifier.weight(1f),
                            ) { Text("Stop Server") }
                        }
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

                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = "$ipAddress:8000",
                                style = MaterialTheme.typography.headlineSmall,
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            TextButton(onClick = {
                                clipboard.setText(AnnotatedString("http://$ipAddress:8000"))
                            }) { Text("Copy") }
                        }

                        Spacer(modifier = Modifier.height(4.dp))

                        Text(
                            text = "Open this address on another device " +
                                    "connected to the same Wi-Fi."
                        )
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(20.dp)) {
                        Text("LAN Password", style = MaterialTheme.typography.titleLarge)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Required before the server will respond to anything on the network.")
                        Spacer(modifier = Modifier.height(8.dp))
                        Button(onClick = { changingPassword = true }) { Text("Change Password") }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                ViewersSection()

                Spacer(modifier = Modifier.height(24.dp))
            }
        }
    }
}

private fun pyModule(name: String) = Python.getInstance().getModule(name)

private fun isPasswordSetPy(): Boolean =
    pyModule("auth_glue").callAttr("is_password_set").toBoolean()

private fun setPasswordPy(password: String) {
    pyModule("auth_glue").callAttr("set_password", password)
}

private fun listViewersPy(): String =
    pyModule("viewers").callAttr("list_viewers_json").toString()

private fun activateViewerPy(name: String, password: String) {
    pyModule("viewers").callAttr("activate_viewer", name, password)
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
