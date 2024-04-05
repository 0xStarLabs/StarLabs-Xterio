from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes


def mnemonic_to_private_key(mnemonic: str):
    seed = Bip39SeedGenerator(mnemonic).Generate()

    bip44_mst_ctx = Bip44.FromSeed(seed, Bip44Coins.ETHEREUM)

    bip44_acc_ctx = bip44_mst_ctx.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    return bip44_acc_ctx.PrivateKey().Raw().ToHex()

