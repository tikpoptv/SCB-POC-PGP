package com.poc.pgp;

import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.SecureRandom;
import java.util.Date;
import java.util.Iterator;

import org.bouncycastle.openpgp.PGPCompressedData;
import org.bouncycastle.openpgp.PGPCompressedDataGenerator;
import org.bouncycastle.openpgp.PGPEncryptedData;
import org.bouncycastle.openpgp.PGPEncryptedDataGenerator;
import org.bouncycastle.openpgp.PGPEncryptedDataList;
import org.bouncycastle.openpgp.PGPLiteralData;
import org.bouncycastle.openpgp.PGPLiteralDataGenerator;
import org.bouncycastle.openpgp.PGPPrivateKey;
import org.bouncycastle.openpgp.PGPPublicKey;
import org.bouncycastle.openpgp.PGPPublicKeyEncryptedData;
import org.bouncycastle.openpgp.PGPPublicKeyRing;
import org.bouncycastle.openpgp.PGPPublicKeyRingCollection;
import org.bouncycastle.openpgp.PGPSecretKeyRingCollection;
import org.bouncycastle.openpgp.PGPUtil;
import org.bouncycastle.openpgp.jcajce.JcaPGPObjectFactory;
import org.bouncycastle.openpgp.operator.jcajce.JcaKeyFingerprintCalculator;
import org.bouncycastle.openpgp.operator.jcajce.JcePBESecretKeyDecryptorBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcePGPDataEncryptorBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcePublicKeyDataDecryptorFactoryBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcePublicKeyKeyEncryptionMethodGenerator;
import org.bouncycastle.util.io.Streams;

public class InMemoryEngine implements PgpEngine {

    private PGPPublicKey publicKey; // กุญแจสาธารณะสำหรับ Encrypt
    private PGPSecretKeyRingCollection privateKeyCollection; // ชุดกุญแจส่วนตัวสำหรับ Decrypt

    @Override
    public String variantId() {
        return "java-inmem-single";
    }

    @Override
    public void loadKeys(String keySetPath) throws Exception {
        // --- 1. โหลด Public Key ---
        File pubFile = new File(keySetPath, "rsa2048-public.asc");
        try (InputStream pubIn = new BufferedInputStream(new FileInputStream(pubFile))) {
            PGPPublicKeyRingCollection pubCollection = new PGPPublicKeyRingCollection(
                PGPUtil.getDecoderStream(pubIn), new JcaKeyFingerprintCalculator());
            
            // --- วนลูปหา Subkey ที่รองรับการ Encryption ---
            Iterator<PGPPublicKeyRing> rIt = pubCollection.getKeyRings();
            if (rIt.hasNext()) {
                Iterator<PGPPublicKey> kIt = rIt.next().getPublicKeys();
                while (kIt.hasNext()) {
                    PGPPublicKey k = kIt.next();
                    if (k.isEncryptionKey()) {
                        this.publicKey = k;
                        break;
                    }
                }
            }
        }

        // --- 2. โหลด Private Key ---
        File privFile = new File(keySetPath, "rsa2048-private.asc");
        try (InputStream privIn = new BufferedInputStream(new FileInputStream(privFile))) {
            this.privateKeyCollection = new PGPSecretKeyRingCollection(
                PGPUtil.getDecoderStream(privIn), new JcaKeyFingerprintCalculator());
        }
    }

    @Override
    public void encrypt(InputStream in, OutputStream out) throws Exception {

        byte[] plaintextBytes = Streams.readAll(in);

        // --- [In-Memory] สร้าง Buffer ใน RAM สำหรับรับข้อมูลที่เข้ารหัสเสร็จแล้ว ---
        ByteArrayOutputStream encBuffer = new ByteArrayOutputStream();

        // --- Bouncy Castle ---
        
        // ชั้นที่ 1 : AES-256 (เข้ารหัสเนื้อหา) + RSA (เข้ารหัสกุญแจ AES)
        PGPEncryptedDataGenerator encGen = new PGPEncryptedDataGenerator(
            new JcePGPDataEncryptorBuilder(PGPEncryptedData.AES_256)
                .setWithIntegrityPacket(true)
                .setSecureRandom(new SecureRandom()).setProvider("BC")
        );
        encGen.addMethod(new JcePublicKeyKeyEncryptionMethodGenerator(publicKey).setProvider("BC"));
        OutputStream encOut = encGen.open(encBuffer, new byte[4096]); // ปลายทางไปที่ Buffer

        // ชั้นที่ 2 : ZLIB บีบอัดข้อมูล
        PGPCompressedDataGenerator compGen = new PGPCompressedDataGenerator(PGPCompressedData.ZLIB);
        OutputStream compOut = compGen.open(encOut); // ปลายทางไปที่ท่อชั้นที่ 1

        // ชั้นที่ 3 : Literal Data สำหรับห่อหุ้ม Metadata (ชื่อไฟล์, วันที่)
        PGPLiteralDataGenerator litGen = new PGPLiteralDataGenerator();
        OutputStream litOut = litGen.open(
            compOut, PGPLiteralData.BINARY, "inline.txt", new Date(), new byte[4096]
        ); // ปลายทางไปที่ท่อชั้นที่ 2

        // --- Stream Pipeline ---
        litOut.write(plaintextBytes);

        // ปิดจากในออกนอกเสมอ
        litOut.close();
        compGen.close();
        encGen.close();

        // นำข้อมูลทั้งหมดที่อยู่ใน RAM เขียนลงไฟล์จริง
        out.write(encBuffer.toByteArray());
    }

    @Override
    public void decrypt(InputStream in, OutputStream out) throws Exception {
        // [In-Memory] โหลด Ciphertext ทั้งหมดขึ้น RAM
        byte[] ciphertextBytes = Streams.readAll(in);

        // สร้าง Factory สำหรับแจกแจงโครงสร้างของไฟล์ PGP
        InputStream decodedIn = PGPUtil.getDecoderStream(new ByteArrayInputStream(ciphertextBytes));
        JcaPGPObjectFactory pgpFact = new JcaPGPObjectFactory(decodedIn);

        // ดึง Object ก้อนแรกออกมา (มักจะเป็น PGPEncryptedDataList)
        Object obj = pgpFact.nextObject();
        PGPEncryptedDataList encList = (obj instanceof PGPEncryptedDataList) 
            ? (PGPEncryptedDataList) obj : (PGPEncryptedDataList) pgpFact.nextObject();

        PGPPublicKeyEncryptedData encData = (PGPPublicKeyEncryptedData) encList.get(0);
        
        // นำ Key ID ของกล่องข้อความ ไปค้นหากุญแจ Private Key
        PGPPrivateKey privKey = privateKeyCollection.getSecretKey(encData.getKeyID())
            .extractPrivateKey(new JcePBESecretKeyDecryptorBuilder().setProvider("BC").build(new char[0]));

        // ได้ Private Key แล้ว เอามาสร้างท่อสำหรับแกะ AES ออก
        InputStream clearStream = encData.getDataStream(
            new JcePublicKeyDataDecryptorFactoryBuilder().setProvider("BC").build(privKey)
        );

        // สร้าง Factory อีกตัวสำหรับอ่านข้อมูลที่ถอด AES ออกแล้ว
        JcaPGPObjectFactory plainFact = new JcaPGPObjectFactory(clearStream);
        Object message = plainFact.nextObject();

        // เช็คข้อมูลข้างในถูกบีบอัดหรือไม่ ถ้าใช่แกะ ZLIB ออก
        if (message instanceof PGPCompressedData) {
            PGPCompressedData compData = (PGPCompressedData) message;
            plainFact = new JcaPGPObjectFactory(compData.getDataStream());
            message = plainFact.nextObject(); // อ่าน Object ถัดไปที่อยู่ข้างใน ZLIB
        }

        // เช็คว่าเป็นข้อมูลดิบ (Literal Data) หรือไม่
        if (message instanceof PGPLiteralData) {
            PGPLiteralData litData = (PGPLiteralData) message;
            try (InputStream litIn = litData.getDataStream()) {
                // ส่งข้อมูลที่แกะเสร็จแล้วออก OutputStream รวดเดียว
                Streams.pipeAll(litIn, out);
            }
        }
    }
}