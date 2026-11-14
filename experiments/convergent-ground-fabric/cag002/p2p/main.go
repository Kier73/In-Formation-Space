// CAG-002: a real libp2p stream transport for immutable CAG packet bytes.
// Peer IDs authenticate individual connections; they are NOT proof of E-CPU
// application admission, stable actor authority, or physical independence.
package main

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"strings"
	"sync"
	"time"

	libp2p "github.com/libp2p/go-libp2p"
	"github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/peer"
	"github.com/libp2p/go-libp2p/core/protocol"
	ma "github.com/multiformats/go-multiaddr"
)

const (
	protocolID = protocol.ID("/cag002/ground-packet/1.0.0")
	maxBytes   = 8192
)

func receive(spool string, addressFile string, dropFirstACK bool) error {
	if spool == "" || addressFile == "" {
		return errors.New("spool and address file are required")
	}
	host, err := libp2p.New(
		libp2p.ListenAddrStrings("/ip4/127.0.0.1/tcp/0"),
		libp2p.DisableRelay(),
	)
	if err != nil {
		return err
	}
	defer host.Close()
	addrs := host.Addrs()
	if len(addrs) == 0 {
		return errors.New("libp2p host has no local listener")
	}
	if err := os.MkdirAll(pathDir(spool), 0755); err != nil {
		return err
	}
	if err := os.MkdirAll(pathDir(addressFile), 0755); err != nil {
		return err
	}
	addr := addrs[0].Encapsulate(ma.StringCast("/p2p/" + host.ID().String()))
	var mu sync.Mutex
	dropped := false
	host.SetStreamHandler(protocolID, func(s network.Stream) {
		defer s.Close()
		_ = s.SetDeadline(time.Now().Add(10 * time.Second))
		line, err := bufio.NewReader(io.LimitReader(s, maxBytes+2)).ReadBytes('\n')
		if err != nil || len(line) > maxBytes+1 || !json.Valid(line) {
			_ = s.Reset()
			return
		}
		var item struct {
			Schema string `json:"schema"`
			Digest string `json:"digest"`
		}
		if err = json.Unmarshal(line, &item); err != nil ||
			item.Schema != "in-formation.cag001-operation/0.1" ||
			len(item.Digest) != 64 {
			_ = s.Reset()
			return
		}
		mu.Lock()
		f, err := os.OpenFile(spool, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
		if err == nil {
			_, err = f.Write(line)
			if err == nil {
				err = f.Sync()
			}
			if cerr := f.Close(); err == nil {
				err = cerr
			}
		}
		shouldDrop := dropFirstACK && !dropped
		if shouldDrop {
			dropped = true
		}
		mu.Unlock()
		if err != nil || shouldDrop {
			// The packet has been fsynced, but its transport ACK is withheld.
			// The sender must retry; duplicate semantic bytes remain visible.
			_ = s.Reset()
			return
		}
		hash := sha256.Sum256(line)
		_, _ = fmt.Fprintf(s, "ACK:%s\n", hex.EncodeToString(hash[:]))
	})
	if err := os.WriteFile(addressFile, []byte(addr.String()+"\n"), 0600); err != nil {
		return err
	}
	fmt.Println("cag002 libp2p listener ready (local test only)")
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	<-ctx.Done()
	return nil
}

func send(addressFile, inputFile string) error {
	if addressFile == "" || inputFile == "" {
		return errors.New("address file and packet file are required")
	}
	b, err := os.ReadFile(inputFile)
	if err != nil {
		return err
	}
	trimmed := []byte(strings.TrimSpace(string(b)))
	if len(trimmed) == 0 || len(trimmed) > maxBytes || !json.Valid(trimmed) {
		return errors.New("invalid or oversized JSON packet")
	}
	trimmed = append(trimmed, '\n')
	addrBytes, err := os.ReadFile(addressFile)
	if err != nil {
		return err
	}
	addr, err := ma.NewMultiaddr(strings.TrimSpace(string(addrBytes)))
	if err != nil {
		return err
	}
	peerInfo, err := peer.AddrInfoFromP2pAddr(addr)
	if err != nil {
		return err
	}
	host, err := libp2p.New(libp2p.NoListenAddrs(), libp2p.DisableRelay())
	if err != nil {
		return err
	}
	defer host.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err = host.Connect(ctx, *peerInfo); err != nil {
		return err
	}
	stream, err := host.NewStream(ctx, peerInfo.ID, protocolID)
	if err != nil {
		return err
	}
	defer stream.Close()
	_ = stream.SetDeadline(time.Now().Add(9 * time.Second))
	if _, err := stream.Write(trimmed); err != nil {
		return err
	}
	ack, err := bufio.NewReader(stream).ReadString('\n')
	if err != nil {
		return fmt.Errorf("missing libp2p transport ACK: %w", err)
	}
	h := sha256.Sum256(trimmed)
	expected := "ACK:" + hex.EncodeToString(h[:]) + "\n"
	if ack != expected {
		return errors.New("libp2p transport ACK does not match sent packet")
	}
	fmt.Println("cag002 libp2p ACK confirmed (not an E-CPU result receipt)")
	return nil
}

func pathDir(path string) string {
	i := strings.LastIndex(path, string(os.PathSeparator))
	if i < 0 {
		return "."
	}
	if i == 0 {
		return string(os.PathSeparator)
	}
	return path[:i]
}

func main() {
	mode := flag.String("mode", "", "serve or send")
	spool := flag.String("spool", "", "fsynced received packet JSONL")
	address := flag.String("address-file", "", "local peer multiaddress")
	input := flag.String("packet-file", "", "packet file for sender")
	drop := flag.Bool("drop-first-ack", false, "simulate post-fsync ACK loss once")
	flag.Parse()
	var err error
	switch *mode {
	case "serve":
		err = receive(*spool, *address, *drop)
	case "send":
		err = send(*address, *input)
	default:
		err = errors.New("mode must be serve or send")
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "CAG-002 libp2p transport failure:", err)
		os.Exit(1)
	}
}
