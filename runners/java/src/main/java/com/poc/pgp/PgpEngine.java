package com.poc.pgp;

import java.io.InputStream;
import java.io.OutputStream;

/**
 * อินเทอร์เฟซของ PGP engine — น้อง implement 2 แบบ:
 *   - InMemoryEngine  (variant "java-inmem-single")
 *   - StreamingEngine (variant "java-stream-single")
 *
 * Profile คงที่: RSA + AES-256 + ZLIB + SHA-256, output แบบ binary
 * รายละเอียด/สัญญา: docs/handoff-java-inmem-variant.md
 *
 * หมายเหตุ: ออกแบบ signature ของเมธอดเอง (ด้านล่างเป็นแค่ไกด์)
 * - in-memory เหมาะกับ byte[] in -> byte[] out
 * - streaming เหมาะกับการทำงานบน InputStream/OutputStream เป็นช่วง ๆ
 *   โดย peak memory ต้องไม่โตตามขนาดไฟล์
 */
public interface PgpEngine {

    /** ตัวระบุ variant เช่น "java-inmem-single" / "java-stream-single" */
    String variantId();

    /** โหลดกุญแจจากโฟลเดอร์ keySetPath (public สำหรับ encrypt, secret สำหรับ decrypt) */
    void loadKeys(String keySetPath) throws Exception;

    /** เข้ารหัส: อ่าน plaintext จาก in แล้วเขียน ciphertext ลง out */
    void encrypt(InputStream in, OutputStream out) throws Exception;

    /** ถอดรหัส: อ่าน ciphertext จาก in แล้วเขียน plaintext ลง out */
    void decrypt(InputStream in, OutputStream out) throws Exception;

    // TODO(น้อง): สร้างคลาส InMemoryEngine และ StreamingEngine ที่ implement interface นี้
}
