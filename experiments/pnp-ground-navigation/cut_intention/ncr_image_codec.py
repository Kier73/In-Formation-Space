"""Native NCR-008 mixed-radix adapter for CIG-qualified temporal images.

The ImageCertificate object is used as a radix layout, NOT an ANF proof.
Only the CIG-025 height verifier qualifies the time-indexed alphabet.
"""
from navigable_compute.realized_image import Factor,ImageCertificate
from navigable_compute.realized_image import pack as ncr_pack,unpack as ncr_unpack


class NCRCodec:
    """Direct execution via the existing Navigable-Compute codec."""
    @staticmethod
    def layout(alphabets,w):
        return ImageCertificate(tuple(
            Factor(tuple(range(j*w,(j+1)*w)),0,values)
            for j,values in enumerate(alphabets)),0)

    def pack(self,alphabets,w,code):
        return ncr_pack(self.layout(alphabets,w),code)

    def unpack(self,alphabets,w,rank):
        return ncr_unpack(self.layout(alphabets,w),rank)
