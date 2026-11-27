"""Verified optional MQTT TLS transport."""

import ssl


def configure_tls(client, settings):
    enabled = settings.get("tls", False)

    if type(enabled) is not bool:
        raise ValueError("mqtt.tls must be boolean")

    if not enabled:
        return

    if settings.get("tls_insecure", False):
        raise ValueError("Insecure TLS is not supported")

    context = ssl.create_default_context(
        cafile=settings.get("tls_ca_file")
    )

    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED

    cert = settings.get("tls_cert_file")
    key = settings.get("tls_key_file")

    if bool(cert) != bool(key):
        raise ValueError(
            "Certificate and key must be configured together"
        )

    if cert:
        context.load_cert_chain(cert, key)

    client.tls_set_context(context)
