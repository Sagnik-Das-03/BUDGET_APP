package com.sd.budgetdashboard

import android.content.Context
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import java.net.Inet4Address
import java.net.NetworkInterface

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            ServerDashboard()
        }
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
                    text = "Android Server",
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