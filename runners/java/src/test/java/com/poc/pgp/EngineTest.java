package com.poc.pgp;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.Security;

import org.bouncycastle.jce.provider.BouncyCastleProvider;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * เทสต์ของน้อง — เขียนเอง
 *
 * อย่างน้อยต้องครอบคลุม:
 *   1) round-trip ของ InMemoryEngine: encrypt แล้ว decrypt ได้ byte เดิมเป๊ะ
 *   2) round-trip ของ StreamingEngine: เช่นเดียวกัน
 *   3) ไฟล์ว่าง (0 byte) round-trip ได้ ไม่ crash
 *   (เสริม) ไฟล์ใหญ่กับ StreamingEngine แล้วยืนยันว่า peak memory ไม่โตตามไฟล์
 *
 * ใช้กุญแจจริงจากโฟลเดอร์ keys/ ของโปรเจกต์ (เช่น path "../../keys")
 *
 * TODO(น้อง): เขียนเทสต์จริงด้วย JUnit 5
 */

public class EngineTest {

    // กำหนดตำแหน่งโฟลเดอร์กุญแจ
    private static final String KEY_SET_PATH = "../../keys";

    @BeforeAll
    public static void setup() {
        // ลงทะเบียน Bouncy Castle Provider ก่อนเริ่มรันเทสต์ทั้งหมด
        Security.addProvider(new BouncyCastleProvider());
    }

    // เทสต์เคสที่ 1: พิสูจน์ Round-trip ของ InMemoryEngine
    @Test
    public void testInMemoryEngineRoundTrip() throws Exception {
        PgpEngine engine = new InMemoryEngine();
        engine.loadKeys(KEY_SET_PATH);

        // 1. เตรียมข้อมูล Plaintext จำลอง
        String originalText = "Hello World! This is a test for InMemory PGP Engine using AES-256.";
        byte[] originalBytes = originalText.getBytes(StandardCharsets.UTF_8);
        InputStream plainIn = new ByteArrayInputStream(originalBytes);
        ByteArrayOutputStream cipherOut = new ByteArrayOutputStream();

        // 2. ทำการ Encrypt
        engine.encrypt(plainIn, cipherOut);
        byte[] ciphertextBytes = cipherOut.toByteArray();
        
        // ยืนยันว่าต้องได้ข้อมูลหลังเข้ารหัส (Ciphertext ต้องไม่ว่างเปล่า)
        assertTrue(ciphertextBytes.length > 0, "Ciphertext should not be empty");

        // 3. ทำการ Decrypt
        InputStream cipherIn = new ByteArrayInputStream(ciphertextBytes);
        ByteArrayOutputStream plainOut = new ByteArrayOutputStream();
        engine.decrypt(cipherIn, plainOut);

        // 4. ตรวจสอบความถูกต้อง
        byte[] decryptedBytes = plainOut.toByteArray();
        assertArrayEquals(originalBytes, decryptedBytes, "Decrypted data must match original bytes exactly.");
    }

    // เทสต์เคสที่ 2: พิสูจน์ Round-trip ของ StreamingEngine
    @Test
    public void testStreamingEngineRoundTrip() throws Exception {
        PgpEngine engine = new StreamingEngine();
        engine.loadKeys(KEY_SET_PATH);

        // 1. เตรียมข้อมูล Plaintext จำลอง
        String originalText = "Hello World! This is a test for Streaming PGP Engine using AES-256.";
        byte[] originalBytes = originalText.getBytes(StandardCharsets.UTF_8);
        InputStream plainIn = new ByteArrayInputStream(originalBytes);
        ByteArrayOutputStream cipherOut = new ByteArrayOutputStream();

        // 2. ทำการ Encrypt
        engine.encrypt(plainIn, cipherOut);
        byte[] ciphertextBytes = cipherOut.toByteArray();
        assertTrue(ciphertextBytes.length > 0);

        // 3. ทำการ Decrypt
        InputStream cipherIn = new ByteArrayInputStream(ciphertextBytes);
        ByteArrayOutputStream plainOut = new ByteArrayOutputStream();
        engine.decrypt(cipherIn, plainOut);

        // 4. ตรวจสอบความถูกต้อง
        byte[] decryptedBytes = plainOut.toByteArray();
        assertArrayEquals(originalBytes, decryptedBytes, "Streaming decrypted data must match original bytes.");
    }

    // เทสต์เคสที่ 3: ตรวจสอบ Edge Case ไฟล์ว่างเปล่า (0 byte)
    @Test
    public void testZeroByteFileRoundTrip() throws Exception {
        // ทดสอบกับทั้งสอง Engine
        PgpEngine[] engines = { new InMemoryEngine(), new StreamingEngine() };

        for (PgpEngine engine : engines) {
            engine.loadKeys(KEY_SET_PATH);

            // 1. เตรียมข้อมูลว่างเปล่า (0 byte)
            byte[] zeroBytes = new byte[0];
            InputStream plainIn = new ByteArrayInputStream(zeroBytes);
            ByteArrayOutputStream cipherOut = new ByteArrayOutputStream();

            // 2. ต้อง Encrypt ได้ (Not throw exception)
            assertDoesNotThrow(() -> {
                engine.encrypt(plainIn, cipherOut);
            }, "Engine " + engine.variantId() + " failed during 0-byte encryption.");

            byte[] ciphertextBytes = cipherOut.toByteArray();

            // 3. ต้อง Decrypt กลับมาได้ข้อมูล 0 byte เท่าเดิม
            InputStream cipherIn = new ByteArrayInputStream(ciphertextBytes);
            ByteArrayOutputStream plainOut = new ByteArrayOutputStream();
            
            assertDoesNotThrow(() -> {
                engine.decrypt(cipherIn, plainOut);
            }, "Engine " + engine.variantId() + " failed during 0-byte decryption.");

            // 4. ตรวจสอบว่าได้ข้อมูล 0 byte
            assertArrayEquals(zeroBytes, plainOut.toByteArray(), 
                "Engine " + engine.variantId() + " did not return 0 bytes back.");
        }
    }
}