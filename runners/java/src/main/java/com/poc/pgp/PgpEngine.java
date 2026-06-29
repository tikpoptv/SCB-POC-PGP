package com.poc.pgp;

import java.io.InputStream;
import java.io.OutputStream;

public interface PgpEngine {
    
    String variantId();

    void loadKeys(String keySetPath) throws Exception;

    void encrypt(InputStream in, OutputStream out) throws Exception;

    void decrypt(InputStream in, OutputStream out) throws Exception;
}